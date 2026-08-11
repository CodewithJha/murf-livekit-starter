"""SIP dial helpers — force narrowband codecs to reduce LiveKit SIP crackle."""

from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp
from livekit import api

logger = logging.getLogger("outbound-sip")


def _http_livekit_url(ws_url: str) -> str:
    url = (ws_url or "").strip().rstrip("/")
    if url.startswith("wss://"):
        return "https://" + url[len("wss://") :]
    if url.startswith("ws://"):
        return "http://" + url[len("ws://") :]
    if url.startswith("https://") or url.startswith("http://"):
        return url
    return "https://" + url


async def create_sip_participant_pcmu(
    *,
    room_name: str,
    sip_trunk_id: str,
    sip_call_to: str,
    participant_identity: str,
    participant_name: str,
) -> dict[str, Any]:
    """Create SIP participant preferring PCMU/PCMA (avoid G.722 chunk artifacts).

    Uses LiveKit Twirp JSON so we can send `media` even when the installed
    protobuf SDK lacks SIPMediaConfig.
    """
    livekit_url = _http_livekit_url(os.getenv("LIVEKIT_URL", ""))
    api_key = os.getenv("LIVEKIT_API_KEY", "")
    api_secret = os.getenv("LIVEKIT_API_SECRET", "")
    if not (livekit_url and api_key and api_secret and sip_trunk_id):
        raise RuntimeError("LiveKit URL/keys/trunk missing for SIP dial")

    token = (
        api.AccessToken(api_key, api_secret)
        .with_identity("outbound-sip-dialer")
        .with_grants(api.VideoGrants(room_join=False, room_admin=True, room=room_name))
        .with_sip_grants(api.SIPGrants(admin=True, call=True))
        .to_jwt()
    )

    body = {
        "sipTrunkId": sip_trunk_id,
        "sipCallTo": sip_call_to,
        "roomName": room_name,
        "participantIdentity": participant_identity,
        "participantName": participant_name,
        "waitUntilAnswered": True,
        "krispEnabled": False,
        # Restrict to G.711 — G.722/wideband re-encode is a known crackle source.
        "media": {
            "onlyListedCodecs": True,
            "codecs": [
                {"name": "PCMU", "rate": 8000},
                {"name": "PCMA", "rate": 8000},
            ],
        },
    }

    endpoint = f"{livekit_url}/twirp/livekit.SIP/CreateSIPParticipant"
    timeout = aiohttp.ClientTimeout(total=90)
    async with (
        aiohttp.ClientSession(timeout=timeout) as session,
        session.post(
            endpoint,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        ) as resp,
    ):
        text = await resp.text()
        if resp.status >= 400:
            logger.error(
                "PCMU SIP dial failed status=%s body=%s — falling back",
                resp.status,
                text[:500],
            )
            raise api.TwirpError(
                code="unavailable",
                msg=text[:300],
                status=resp.status,
                metadata={},
            )
        logger.info("SIP participant created with PCMU/PCMA media preference")
        try:
            return await resp.json()
        except Exception:
            return {"raw": text}
