"""Murf TTS for telephony — full download + realtime-paced 20ms frames.

LiveKit Cloud SIP mixer underruns when audio is dumped in bursts (default
200ms emitter frames or instant full-buffer push into a small WebRTC queue).
Symptom: ~0.2s drop / crackle every few words.

Strategy:
1. Download the full PCM from Murf first.
2. Emit 20ms frames with a short prebuffer, then sleep in realtime so the
   SIP bridge never starves or overflows.
"""

from __future__ import annotations

import asyncio
import logging
import time

import aiohttp
from livekit.agents import (
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    APITimeoutError,
    tts,
    utils,
)
from livekit.agents.types import DEFAULT_API_CONNECT_OPTIONS
from livekit.plugins import murf

logger = logging.getLogger("smooth-murf-tts")

_API_AUTH_HEADER = "api-key"
_FRAME_MS = 20
# Larger head-start for narrowband SIP (8 kHz / PCMU).
_PREBUFFER_MS = 600


class SmoothMurfTTS(murf.TTS):
    """Murf Falcon TTS paced for SIP/Linphone."""

    def synthesize(
        self,
        text: str,
        *,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> tts.ChunkedStream:
        return _PacedBufferedStream(
            tts=self, input_text=text, conn_options=conn_options
        )


class _PacedBufferedStream(tts.ChunkedStream):
    def __init__(
        self, *, tts: SmoothMurfTTS, input_text: str, conn_options: APIConnectOptions
    ) -> None:
        super().__init__(tts=tts, input_text=input_text, conn_options=conn_options)
        self._murf = tts

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        opts = self._murf._opts
        request_id = utils.shortuuid()
        started = time.perf_counter()
        sample_rate = opts.sample_rate
        bytes_per_frame = int(sample_rate * _FRAME_MS / 1000) * 2  # s16le mono
        prebuffer_frames = max(1, _PREBUFFER_MS // _FRAME_MS)

        try:
            async with self._murf._ensure_session().post(
                opts.get_http_url("/v1/speech/stream"),
                headers={_API_AUTH_HEADER: opts.api_key},
                json={
                    "text": self._input_text,
                    "model": opts.model,
                    "multiNativeLocale": opts.locale,
                    "voice_id": opts.voice,
                    "style": opts.style,
                    "rate": opts.speed,
                    "pitch": opts.pitch,
                    "format": opts.encoding,
                    "sample_rate": sample_rate,
                },
                timeout=aiohttp.ClientTimeout(
                    total=60, sock_connect=self._conn_options.timeout
                ),
            ) as resp:
                resp.raise_for_status()
                pcm = await resp.read()

            if not pcm:
                raise APIConnectionError("Murf returned empty audio")

            # Pad to whole frames so the last slice is not truncated oddly.
            remainder = len(pcm) % bytes_per_frame
            if remainder:
                pcm += b"\0" * (bytes_per_frame - remainder)

            logger.info(
                "pacing Murf utterance bytes=%s frames=%s prebuffer_frames=%s "
                "ttfb_full_ms=%.0f request_id=%s",
                len(pcm),
                len(pcm) // bytes_per_frame,
                prebuffer_frames,
                (time.perf_counter() - started) * 1000.0,
                request_id,
            )

            output_emitter.initialize(
                request_id=request_id,
                sample_rate=sample_rate,
                num_channels=1,
                mime_type="audio/pcm",
                frame_size_ms=_FRAME_MS,
            )

            loop = asyncio.get_event_loop()
            # Wall-clock pacing from the moment we start feeding audio.
            t0 = loop.time()
            frame_idx = 0
            for offset in range(0, len(pcm), bytes_per_frame):
                output_emitter.push(pcm[offset : offset + bytes_per_frame])
                frame_idx += 1
                if frame_idx <= prebuffer_frames:
                    continue
                # Stay ahead by prebuffer, but never dump faster than realtime.
                target = t0 + (frame_idx - prebuffer_frames) * (_FRAME_MS / 1000.0)
                delay = target - loop.time()
                if delay > 0.001:
                    await asyncio.sleep(delay)

            output_emitter.flush()

        except asyncio.TimeoutError as exc:
            raise APITimeoutError() from exc
        except aiohttp.ClientResponseError as exc:
            raise APIStatusError(
                message=exc.message,
                status_code=exc.status,
                request_id=None,
                body=None,
            ) from exc
        except APIConnectionError:
            raise
        except Exception as exc:
            raise APIConnectionError() from exc
