import logging
import re
from typing import Any

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    ChatContext,
    ChatMessage,
    JobContext,
    JobProcess,
    RunContext,
    cli,
    function_tool,
    room_io,
    tokenize,
)
from livekit.agents.llm.tool_context import ToolFlag
from livekit.plugins import deepgram, google, murf, noise_cancellation, silero
from livekit.plugins.turn_detector.multilingual import MultilingualModel

from catalogue import CatalogueStore
from escalation_store import EscalationStore
from memory_store import MemoryStore

logger = logging.getLogger("agent")

load_dotenv(".env.local")

_memory_store = MemoryStore()
_catalogue_store = CatalogueStore()
_escalation_store = EscalationStore()

# Voice for Bharat 2026 — Local Commerce (kirana order taking) + Day 4 memory + Day 5 tools.
# Voice: Anisha — locale switches to hi-IN only for clear Hindi/Hinglish turns.
SYSTEM_PROMPT = """
IDENTITY
You are Dukaan Dost, the voice order assistant for a small Indian kirana shop.
You take spoken grocery orders. You are not the shopkeeper. Final bill and delivery stay with the shopkeeper.

OBJECTIVES
On every order turn:
1. Listen for item names and quantities.
2. Repeat each item and quantity back clearly so the customer can correct you.
3. When the caller asks about stock, availability, or indicative price — call lookup_kirana_item before answering.
4. Ask if they want anything else.
5. When they are done, read a short order summary and say the shopkeeper will confirm the final bill, stock, and delivery.

Example English replies:
- "Got it — two litres of milk. Anything else?"
- "Noted: one kilo atta and two packets biscuits. Shall I add more?"
- "Your list so far: two litres milk, one kilo tomatoes. Shopkeeper will confirm price and delivery."

Example Hindi replies (only when customer spoke Hindi/Hinglish) — Devanagari only:
- "जी, दो लीटर दूध नोट कर लिया। और कुछ चाहिए?"
- "एक किलो आटा और दो पैकेट बिस्किट। और कुछ?"

Never reply with empty filler like only "Haan ji", "Okay ji", "Theek hai", "हाँ जी" without naming the item and quantity.

MEMORY — use tools, never invent saved history
Tools: lookup_caller, save_caller_memory, lookup_kirana_item, create_escalation.
- After you greet (or as soon as the caller shares their name), call lookup_caller with their name.
- If a profile is found: greet/welcome them by name, briefly continue from last time using their facts (past orders, usual quantities, preferred delivery slot), then take today's order.
- If not found: treat them as a new customer, ask their name if still unknown, then take the order.
- After you learn useful kirana facts (name, usual quantities, past/current order summary, preferred delivery slot), ASK before saving. Example: "Shall I remember this for next time?"
- Call save_caller_memory only after a clear yes. Set caller_consented=true only then.
- If they say no, do not save. You may call save_caller_memory with caller_consented=false, or simply skip saving.
- Never claim you remembered something you did not save via the tool.
- Do not call tools on the very first greeting turn before the user has spoken.

CATALOGUE — lookup_kirana_item
- Call when the caller asks if something is in stock, available, how much it costs, or wants an approximate line total.
- Pass the spoken item name (English is fine: onion, tomato, milk). Optionally pass quantity for an indicative total.
- Speak only facts returned by the tool. Mention it is indicative / from today's catalogue list, and the shopkeeper confirms the final bill.
- If found=false or error: say you could not find it in the list and offer to note it for the shopkeeper. Never invent stock or prices.
- You may still take the order line even when the catalogue misses — note it for the shopkeeper.

HUMAN HELP — create_escalation (only two cases)
Use create_escalation ONLY when the caller needs a human shopkeeper for:
1. payment_refund_dispute — charged wrong, wants refund, UPI/payment issue, double charge.
2. order_dispute — wrong/missing items, damaged goods, delivery complaint about a past order.

Do NOT escalate for normal order-taking ("two litres milk", price checks, new orders).
Before calling create_escalation:
- Explain briefly what you will share with the shopkeeper (name, issue summary, what you already checked).
- Ask clear permission: "Shall I pass this to the shopkeeper for follow-up?"
- Call create_escalation only after a clear yes. Set caller_consented=true only then.
- If they refuse, do not create. You may call with caller_consented=false or skip.
After a successful create:
- Give the reference ID (ESC-…) clearly.
- Say the shopkeeper will review and follow up. Do NOT promise an instant callback or refund.
- Do not take OTPs, PINs, card numbers, or full payment details — ever.

KNOWLEDGE
Common kirana items: milk/दूध, atta/आटा, rice/चावल, oil/तेल, sugar/चीनी, tea/चाय, biscuits, eggs/अंडे, onions/प्याज, tomatoes/टमाटर, potatoes/आलू, and similar.
If an item is unclear, ask one short clarifying question. Do not invent stock, prices, or delivery times outside tool results.

LANGUAGE & SCRIPT — follow strictly
Always write every language in its own native script.
- Hindi → Devanagari (नमस्ते), never romanized (never "namaste", "doodh", "chahiye" in replies).
- English → Latin script.
Default: simple Indian English.
Match ONLY the customer's latest turn:
- Clear English (hi, hello, "two litres milk", "I want to order…") → reply in Indian English. Do NOT use Hindi.
- Clear Hindi or Hinglish (नमस्ते, "mujhe chahiye", "ek kilo doodh dena", or Devanagari) → reply in simple Hindi in Devanagari script.
- Hindi item words inside an English sentence ("one kilo doodh") → stay in English and confirm the item.
When a system note specifies the language for this turn, obey it exactly.
Do not flip languages randomly. Do not greet in Hindi after an English "hi".

GUARDRAILS
Never take payments, OTPs, or card details.
Never invent prices or stock — only report catalogue tool results as indicative.
Never confirm a final bill total, stock guarantee, or delivery time as booked.
Never claim the order is fully booked.
If they ask for delivery timing: note it for the shopkeeper and keep taking items.
Refuse medical, legal, financial, or illegal help.

STYLE
Spoken aloud. One or two short sentences. No bullets, markdown, or emojis.
Always include the item name and quantity when acknowledging an order line.

FIRST TURN
Greet immediately as Dukaan Dost without waiting on tools.
- New caller (English): "Hi, I'm Dukaan Dost for the kirana shop. May I have your name, and what would you like to order?"
- New caller (Hindi): "नमस्ते, मैं दूकान दोस्त हूँ। आपका नाम बताइए और क्या ऑर्डर करना है?"
As soon as you hear a name (or anytime you need saved facts), call lookup_caller with that name.
If a profile is found after lookup: welcome them by name, mention one saved fact, then continue the order.
"""

# Grocery keyterms boost Deepgram Nova-3 recognition (English + common romanized Hindi).
_STT_KEYTERMS = [
    "milk",
    "doodh",
    "atta",
    "flour",
    "rice",
    "chawal",
    "oil",
    "tel",
    "sugar",
    "cheeni",
    "tea",
    "chai",
    "biscuit",
    "biscuits",
    "eggs",
    "ande",
    "onion",
    "pyaz",
    "tomato",
    "tomatoes",
    "tamatar",
    "potato",
    "aloo",
    "litre",
    "liter",
    "kilo",
    "kilogram",
    "packet",
    "packets",
    "kirana",
    "order",
    "namaste",
]

# Strong Hindi/Hinglish signals only — avoid weak words like "ji" / "hai" that false-trigger.
_HINDI_STRONG = (
    "namaste",
    "namaskar",
    "chahiye",
    "dijiye",
    "diijiye",
    "dena",
    "doona",
    "mujhe",
    "mera",
    "meri",
    "mere",
    "aapko",
    "kitna",
    "kitne",
    "sunao",
    "bolo",
    "doodh",
    "chawal",
    "sabzi",
    "atta",
    "cheeni",
    "pyaz",
    "tamatar",
    "aloo",
    "bhaiya",
    "bhai",
    "kripya",
    "kripa",
)

_ENGLISH_GREETINGS = {
    "hello",
    "hi",
    "hey",
    "hello.",
    "hi.",
    "hey.",
    "good morning",
    "good evening",
    "good afternoon",
}


def _reply_locale_for_text(text: str) -> str:
    """Pick reply/TTS locale from the user's latest utterance. Prefer English unless Hindi is clear."""
    raw = (text or "").strip()
    if not raw:
        return "en-IN"

    # Devanagari script → Hindi
    if any("\u0900" <= ch <= "\u097f" for ch in raw):
        return "hi-IN"

    lower = raw.lower().strip()
    if lower in _ENGLISH_GREETINGS or lower.rstrip(".!") in _ENGLISH_GREETINGS:
        return "en-IN"

    # Clear English order phrasing
    if re.search(
        r"\b(i want|i'd like|please|order|litre|liter|kilo|packet|kg|ml)\b",
        lower,
    ) and not any(m in lower for m in ("chahiye", "dijiye", "dena", "mujhe")):
        return "en-IN"

    words = [re.sub(r"[^\w]+", "", w) for w in lower.split()]
    words = [w for w in words if w]
    strong_hits = sum(1 for w in words if w in _HINDI_STRONG)
    phrase_hits = sum(1 for m in _HINDI_STRONG if len(m) > 3 and m in lower)

    if strong_hits >= 2 or phrase_hits >= 2:
        return "hi-IN"
    if strong_hits >= 1 and len(words) <= 8:
        return "hi-IN"
    return "en-IN"


def _session_identity(context: RunContext) -> str:
    try:
        userdata = context.userdata
    except ValueError:
        return ""
    if isinstance(userdata, dict):
        return str(userdata.get("livekit_identity") or "")
    return ""


def _set_active_user_id(context: RunContext, user_id: str) -> None:
    try:
        userdata = context.userdata
    except ValueError:
        return
    if isinstance(userdata, dict):
        userdata["active_user_id"] = user_id


class Assistant(Agent):
    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        catalogue_store: CatalogueStore | None = None,
        escalation_store: EscalationStore | None = None,
    ) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self._memory = memory_store or _memory_store
        self._catalogue = catalogue_store or _catalogue_store
        self._escalations = escalation_store or _escalation_store

    async def on_enter(self) -> None:
        # Gemini rejects tool-call→reply on enter ("function call turn must follow
        # user/function-response"). Greet without tools; lookup runs after the
        # caller shares their name (still via function tools).
        await self.session.generate_reply(
            instructions=(
                "Greet as Dukaan Dost for the kirana shop in one short spoken "
                "sentence. Ask for their name and what they would like to order. "
                "Do not call any tools on this turn."
            ),
            tool_choice="none",
        )

    async def on_user_turn_completed(
        self, turn_ctx: ChatContext, new_message: ChatMessage
    ) -> None:
        text = new_message.text_content or ""
        locale = _reply_locale_for_text(text)

        tts = getattr(self.session, "tts", None)
        if tts is not None and hasattr(tts, "update_options"):
            # Always set locale both ways so Hindi does not stick after English turns.
            tts.update_options(locale=locale)
            logger.info("Reply locale %s for user text: %r", locale, text[:80])

        # Prefer instruction hints over extra system turns — Gemini is strict about
        # turn order when tools are in the chat history.
        if locale == "hi-IN":
            turn_ctx.add_message(
                role="system",
                content=(
                    "Language for this reply: Hindi in Devanagari script only "
                    "(e.g. नमस्ते, दूध). Never romanize Hindi. "
                    "Confirm item name + quantity. "
                    "Do not answer with empty filler like only 'हाँ जी'."
                ),
            )
        else:
            turn_ctx.add_message(
                role="system",
                content=(
                    "Language for this reply: Indian English only. "
                    "Confirm item name + quantity in English. "
                    "Do not use Hindi words or 'ji' filler. "
                    "Example: 'Got it — two litres of milk. Anything else?'"
                ),
            )

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def lookup_caller(
        self,
        context: RunContext,
        name: str = "",
    ) -> dict[str, Any]:
        """Look up a returning caller in the shop memory database.

        Call at the start of a conversation and again whenever the caller shares
        their name. Facts come only from this tool — never invent memory.

        Args:
            name: Caller's name if known. Leave empty to try LiveKit identity only.
        """
        identity = _session_identity(context)
        profile = None
        if name and name.strip():
            profile = self._memory.lookup_by_name(name.strip())
        if profile is None and identity:
            profile = self._memory.lookup_by_identity(identity)

        if profile is None:
            logger.info(
                "lookup_caller: miss name=%r identity=%r", name, identity or None
            )
            return {
                "found": False,
                "message": "No saved caller profile. Treat them as a new customer.",
            }

        _set_active_user_id(context, profile.user_id)
        logger.info("lookup_caller: hit user_id=%s", profile.user_id)
        return {"found": True, **profile.to_dict()}

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def save_caller_memory(
        self,
        context: RunContext,
        name: str,
        language_preference: str,
        past_orders: str,
        usual_quantities: str,
        preferred_delivery_slot: str,
        caller_consented: bool,
    ) -> dict[str, Any]:
        """Save caller identity and kirana facts ONLY after explicit consent.

        Ask first (e.g. "Shall I remember this for next time?"). Set
        caller_consented=True only if they clearly agreed. If they refuse, set
        caller_consented=False — nothing will be written.

        Args:
            name: Caller's name.
            language_preference: Preferred reply locale, en-IN or hi-IN.
            past_orders: Short summary of recent or current order items.
            usual_quantities: Habitual quantities (e.g. always two litres milk).
            preferred_delivery_slot: Preferred delivery window (e.g. evening 6-8).
            caller_consented: True only after the caller explicitly agreed to save.
        """
        if not caller_consented:
            logger.info("save_caller_memory: declined for name=%r", name)
            return {
                "saved": False,
                "reason": "Caller declined or consent missing. Nothing was written.",
            }

        if not (name or "").strip():
            return {
                "saved": False,
                "reason": "Name is required before saving.",
            }

        identity = _session_identity(context) or None
        profile = self._memory.save(
            name=name.strip(),
            language_preference=language_preference or "en-IN",
            facts={
                "past_orders": past_orders or "",
                "usual_quantities": usual_quantities or "",
                "preferred_delivery_slot": preferred_delivery_slot or "",
            },
            livekit_identity=identity,
        )
        _set_active_user_id(context, profile.user_id)
        logger.info("save_caller_memory: saved user_id=%s", profile.user_id)
        return {"saved": True, "profile": profile.to_dict()}

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def lookup_kirana_item(
        self,
        context: RunContext,
        item_name: str,
        quantity: float = 0,
    ) -> dict[str, Any]:
        """Look up kirana stock and indicative price from the local catalogue CSV.

        Call when the caller asks about availability, stock, price, or an
        approximate line total. Never invent catalogue facts — speak only what
        this tool returns. Prices are indicative; shopkeeper confirms the bill.

        Args:
            item_name: Spoken item to search (e.g. onion, tomato, milk).
            quantity: Optional pack/kilo count for an indicative line total.
                Pass 0 to skip the total estimate.
        """
        query = (item_name or "").strip()
        if not query:
            return {
                "found": False,
                "error": False,
                "message": "Need an item name to look up.",
            }

        if quantity and float(quantity) > 0:
            result = self._catalogue.estimate_line_total(query, float(quantity))
        else:
            result = self._catalogue.lookup(query)

        logger.info(
            "lookup_kirana_item: query=%r found=%s stock=%s",
            query,
            result.get("found"),
            result.get("stock_status"),
        )
        return result

    @function_tool(flags=ToolFlag.IGNORE_ON_ENTER)
    async def create_escalation(
        self,
        context: RunContext,
        reason: str,
        what_happened: str,
        already_checked: str,
        urgency: str,
        preferred_followup: str,
        caller_name: str,
        language: str,
        caller_consented: bool,
    ) -> dict[str, Any]:
        """Create a human-help request for the shopkeeper ONLY after explicit consent.

        Use only for payment/refund disputes or order disputes — not for normal
        grocery ordering. Ask permission first and explain what will be shared.

        Args:
            reason: payment_refund_dispute or order_dispute.
            what_happened: Short 1-2 sentence summary (no OTP/PIN/card details).
            already_checked: What you already tried (catalogue lookup, order note, etc.).
            urgency: low, medium, or high (default medium).
            preferred_followup: How they want follow-up (call back, WhatsApp, in-shop).
            caller_name: Caller's name.
            language: en-IN or hi-IN.
            caller_consented: True only after the caller explicitly agreed to escalate.
        """
        _ = context
        logger.info(
            "create_escalation: reason=%r consented=%s caller=%r",
            reason,
            caller_consented,
            caller_name,
        )
        return self._escalations.create(
            reason=reason,
            what_happened=what_happened,
            already_checked=already_checked,
            urgency=urgency or "medium",
            preferred_followup=preferred_followup or "",
            caller_name=caller_name,
            language=language or "en-IN",
            caller_consented=caller_consented,
        )


server = AgentServer(num_idle_processes=1)


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Join the room FIRST so the frontend sees the agent before any LLM/TTS work.
    # Starting the session before connect caused "Agent did not join the room"
    # (on_enter TTS ran while ctx.connect() was still pending / timing out).
    await ctx.connect()

    livekit_identity = "console-user"
    if not ctx.is_fake_job():
        # Prefer an already-present caller; otherwise wait briefly.
        remotes = list(ctx.room.remote_participants.values())
        if remotes:
            livekit_identity = remotes[0].identity
        else:
            participant = await ctx.wait_for_participant()
            livekit_identity = participant.identity
    logger.info("Caller LiveKit identity: %s", livekit_identity)

    session = AgentSession(
        stt=deepgram.STT(
            model="nova-3",
            language="multi",
            interim_results=True,
            punctuate=True,
            smart_format=True,
            numerals=True,
            # Default 25ms cuts speech mid-phrase; give the user time to finish.
            endpointing_ms=400,
            keyterm=_STT_KEYTERMS,
        ),
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
        tts=murf.TTS(
            voice="Anisha",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
            verbose=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        # Keep False for Day 3 listening quality (fuller transcript before reply).
        preemptive_generation=False,
        userdata={
            "livekit_identity": livekit_identity,
            "active_user_id": "",
        },
    )

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params: (
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind
                    == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )


if __name__ == "__main__":
    cli.run_app(server)
