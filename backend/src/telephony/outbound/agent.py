"""Outbound Dukaan Dost — order confirmation calls (Voice for Bharat Day 6).

Unlike the browser agent, this worker dials out via LiveKit SIP after dispatch.

Run the worker:

    uv run python src/telephony/outbound/agent.py start

Then place a call:

    uv run python src/telephony/outbound/dial.py --to sip:user@sip.linphone.org \\
        --name Priyanshu --order "two litres milk and one kilo onion"

See src/telephony/README.md for Linphone / Twilio trunk setup.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from livekit import api
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    room_io,
)
from livekit.plugins import deepgram, google, silero

# Allow imports when running this file directly (uv run python src/telephony/outbound/agent.py).
_SRC_ROOT = Path(__file__).resolve().parents[2]
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from memory_store import MemoryStore  # noqa: E402
from telephony.outbound.call_context import (  # noqa: E402
    OutboundCallContext,
    build_greeting,
    build_system_prompt,
    call_context_from_metadata,
)
from telephony.outbound.sip_dial import create_sip_participant_pcmu  # noqa: E402
from telephony.outbound.smooth_tts import SmoothMurfTTS  # noqa: E402

logger = logging.getLogger("outbound-agent")

load_dotenv(".env.local")

OUTBOUND_TRUNK_ID = os.getenv("LIVEKIT_SIP_OUTBOUND_TRUNK_ID")
CALLEE_IDENTITY = "phone-user"

_memory_store = MemoryStore()


class OutboundAssistant(Agent):
    def __init__(
        self,
        ctx: JobContext,
        call_ctx: OutboundCallContext,
        memory: MemoryStore | None = None,
    ) -> None:
        super().__init__(instructions=build_system_prompt(call_ctx))
        self.ctx = ctx
        self.call_ctx = call_ctx
        self._memory = memory or _memory_store

    @function_tool
    async def confirm_order(
        self,
        context: RunContext,
        confirmed: bool,
        final_order: str,
        notes: str = "",
    ) -> dict:
        """Record whether the customer confirmed today's grocery order.

        Call after they say the order is correct, or after they give corrections.

        Args:
            confirmed: True if they accepted the order (with any corrections applied).
            final_order: The final item list to note for the shopkeeper.
            notes: Optional short note (e.g. delivery preference request).
        """
        order_text = (final_order or self.call_ctx.order_summary).strip()
        logger.info(
            "confirm_order: confirmed=%s order=%r notes=%r",
            confirmed,
            order_text,
            notes,
        )
        name = self.call_ctx.customer_name.strip()
        if name:
            facts = {
                "past_orders": order_text,
                "last_outbound_confirmation": (
                    "confirmed" if confirmed else "needs_review"
                ),
            }
            if notes:
                facts["outbound_notes"] = notes
            try:
                self._memory.save(
                    name=name,
                    language_preference=self.call_ctx.locale,
                    facts=facts,
                )
            except ValueError:
                logger.exception("confirm_order: could not save memory")

        if confirmed:
            return {
                "saved": True,
                "confirmed": True,
                "final_order": order_text,
                "message": (
                    "Order noted as confirmed for the shopkeeper. "
                    "Thank them briefly, then use end_call."
                ),
            }
        return {
            "saved": True,
            "confirmed": False,
            "final_order": order_text,
            "message": (
                "Corrections noted for the shopkeeper. "
                "Read back the updated list, then use end_call when done."
            ),
        }

    @function_tool
    async def opt_out_of_calls(self, context: RunContext) -> dict:
        """Stop future outbound confirmation calls for this customer.

        Use when they say stop calling, don't call again, or similar opt-out.
        """
        name = self.call_ctx.customer_name.strip() or "unknown"
        logger.info("opt_out_of_calls: name=%r", name)
        if self.call_ctx.customer_name.strip():
            try:
                self._memory.save(
                    name=self.call_ctx.customer_name.strip(),
                    language_preference=self.call_ctx.locale,
                    facts={"outbound_opt_out": True},
                )
            except ValueError:
                logger.exception("opt_out_of_calls: could not save memory")
        return {
            "opted_out": True,
            "message": (
                "Acknowledge briefly that you will not call again, then use end_call."
            ),
        }

    @function_tool
    async def detected_answering_machine(self, context: RunContext) -> str:
        """Hang up because the call reached voicemail or an answering machine.

        Use as soon as you hear a recorded greeting rather than a live person.
        """
        logger.info("answering machine detected — hanging up")
        await self._hangup()
        return "Call ended."

    @function_tool
    async def end_call(self, context: RunContext) -> str:
        """Hang up after the conversation is finished.

        Say a short goodbye first (via generate_reply), then call this tool.
        """
        await context.session.generate_reply(
            instructions=(
                "Thank them warmly in two short sentences: say the order is noted "
                "for the shopkeeper, then a friendly goodbye. Do not ask another question."
            ),
            tool_choice="none",
        )
        logger.info("ending outbound call")
        await self._hangup()
        return "Call ended."

    async def _hangup(self) -> None:
        """Delete the room, which drops the SIP leg and ends the phone call."""
        try:
            await self.ctx.api.room.delete_room(
                api.DeleteRoomRequest(room=self.ctx.room.name)
            )
        except Exception:
            logger.exception("hangup failed for room=%s", self.ctx.room.name)


server = AgentServer(num_idle_processes=1)


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="outbound-agent")
async def outbound_agent(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    call_ctx = call_context_from_metadata(ctx.job.metadata)
    if call_ctx is None:
        logger.error(
            "no phone_number in job metadata — dispatch with "
            '{"phone_number": "sip:user@sip.linphone.org", '
            '"customer_name": "Priyanshu", "order_summary": "…"}'
        )
        ctx.shutdown()
        return

    if not OUTBOUND_TRUNK_ID:
        logger.error("LIVEKIT_SIP_OUTBOUND_TRUNK_ID is not set — cannot place calls")
        ctx.shutdown()
        return

    # Enrich order from Day 4 memory when dialer did not pass a specific list.
    if call_ctx.customer_name.strip():
        profile = _memory_store.lookup_by_name(call_ctx.customer_name)
        if profile is not None:
            if profile.facts.get("outbound_opt_out") is True:
                logger.warning(
                    "customer %r opted out of outbound calls — aborting dial",
                    call_ctx.customer_name,
                )
                ctx.shutdown()
                return
            past = str(profile.facts.get("past_orders") or "").strip()
            if past and call_ctx.order_summary in {
                "your grocery order",
                "",
            }:
                call_ctx = OutboundCallContext(
                    phone_number=call_ctx.phone_number,
                    customer_name=call_ctx.customer_name or profile.name,
                    order_summary=past,
                    locale=call_ctx.locale
                    if call_ctx.locale != "en-IN"
                    else (profile.language_preference or "en-IN"),
                )

    await ctx.connect()

    greeting = build_greeting(call_ctx)
    locale = call_ctx.locale

    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="multi",
            interim_results=True,
            punctuate=True,
            smart_format=True,
            numerals=True,
            endpointing_ms=700,
        ),
        llm=google.LLM(model="gemini-3.5-flash-lite"),
        tts=SmoothMurfTTS(
            voice="Anisha",
            style="Conversation",
            speed=-8,
            text_pacing=False,
            # 8 kHz matches PCMU on the SIP leg — avoids 24k→Opus→8k re-encode crackle.
            sample_rate=8000,
            streaming=False,
            verbose=False,
        ),
        turn_detection="vad",
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=False,
        allow_interruptions=False,
        min_endpointing_delay=0.8,
        max_endpointing_delay=3.0,
        aec_warmup_duration=3.0,
        userdata={
            "livekit_identity": CALLEE_IDENTITY,
            "customer_name": call_ctx.customer_name,
            "order_summary": call_ctx.order_summary,
        },
    )

    # Warm models while the phone rings.
    session_started = asyncio.create_task(
        session.start(
            agent=OutboundAssistant(ctx, call_ctx),
            room=ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=room_io.AudioInputOptions(
                    sample_rate=8000,
                    frame_size_ms=20,
                    noise_cancellation=None,
                ),
                audio_output=room_io.AudioOutputOptions(
                    sample_rate=8000,
                    num_channels=1,
                ),
            ),
        )
    )

    logger.info(
        "dialing %s for order=%r", call_ctx.phone_number, call_ctx.order_summary
    )
    try:
        try:
            await create_sip_participant_pcmu(
                room_name=ctx.room.name,
                sip_trunk_id=OUTBOUND_TRUNK_ID,
                sip_call_to=call_ctx.phone_number,
                participant_identity=CALLEE_IDENTITY,
                participant_name=call_ctx.display_name,
            )
        except Exception as media_exc:
            # Older Cloud projects may reject media {}; fall back to SDK dial.
            logger.warning(
                "PCMU-restricted dial failed (%s); retrying standard SIP dial",
                media_exc,
            )
            await ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=OUTBOUND_TRUNK_ID,
                    sip_call_to=call_ctx.phone_number,
                    participant_identity=CALLEE_IDENTITY,
                    participant_name=call_ctx.display_name,
                    wait_until_answered=True,
                    krisp_enabled=False,
                )
            )
    except api.TwirpError as e:
        logger.error(
            "call to %s was not answered: %s (%s)",
            call_ctx.phone_number,
            e.message,
            e.metadata.get("sip_status") if e.metadata else None,
        )
        session_started.cancel()
        ctx.shutdown()
        return

    await session_started

    tts = getattr(session, "tts", None)
    if tts is not None and hasattr(tts, "update_options"):
        tts.update_options(locale=locale)

    # Speak first — do not allow interruptions on the opening (echo cuts audio).
    await session.say(greeting, allow_interruptions=False)


if __name__ == "__main__":
    cli.run_app(server)
