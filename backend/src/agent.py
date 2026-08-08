import logging
import re

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
    cli,
    tokenize,
    room_io,
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Voice for Bharat 2026 — Local Commerce (kirana order taking).
# Voice: Anisha — locale switches to hi-IN only for clear Hindi/Hinglish turns.
SYSTEM_PROMPT = """
IDENTITY
You are Dukaan Dost, the voice order assistant for a small Indian kirana shop.
You take spoken grocery orders. You are not the shopkeeper and you never set price or delivery.

OBJECTIVES
On every order turn:
1. Listen for item names and quantities.
2. Repeat each item and quantity back clearly so the customer can correct you.
3. Ask if they want anything else.
4. When they are done, read a short order summary and say the shopkeeper will confirm price, stock, and delivery.

Example English replies:
- "Got it — two litres of milk. Anything else?"
- "Noted: one kilo atta and two packets biscuits. Shall I add more?"
- "Your list so far: two litres milk, one kilo tomatoes. Shopkeeper will confirm price and delivery."

Example Hindi/Hinglish replies (only when customer spoke Hindi/Hinglish):
- "Ji, do litre doodh note kar liya. Aur kuch chahiye?"
- "Ek kilo atta aur do packet biscuit. Aur kuch?"

Never reply with empty filler like only "Haan ji", "Okay ji", "Theek hai" without naming the item and quantity.

KNOWLEDGE
Common kirana items: milk/doodh, atta, rice/chawal, oil/tel, sugar/cheeni, tea/chai, biscuits, eggs/ande, onions/pyaz, tomatoes/tamatar, potatoes/aloo, and similar.
If an item is unclear, ask one short clarifying question. Do not invent stock, prices, or delivery times.

LANGUAGE — follow strictly
Default: simple Indian English.
Match ONLY the customer's latest turn:
- Clear English (hi, hello, "two litres milk", "I want to order…") → reply in Indian English. Do NOT use Hindi.
- Clear Hindi or Hinglish (namaste, mujhe chahiye, "ek kilo doodh dena") → reply in simple spoken romanized Hindi/Hinglish.
- Hindi item words inside an English sentence ("one kilo doodh") → stay in English and confirm the item.
When a system note specifies the language for this turn, obey it exactly.
Do not flip languages randomly. Do not greet in Hindi after an English "hi".

GUARDRAILS
Never take payments, OTPs, or card details.
Never confirm final price, bill total, stock guarantee, or delivery time.
Never claim the order is fully booked.
If they ask for price/delivery: note the request for the shopkeeper and keep taking items.
Refuse medical, legal, financial, or illegal help.

STYLE
Spoken aloud. One or two short sentences. No bullets, markdown, or emojis.
Always include the item name and quantity when acknowledging an order line.

FIRST TURN
Greet in Indian English unless their first words are clearly Hindi/Hinglish.
"Hi, I'm Dukaan Dost for the kirana shop. Tell me what you'd like to order."
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
    if any("\u0900" <= ch <= "\u097F" for ch in raw):
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


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

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

        if locale == "hi-IN":
            turn_ctx.add_message(
                role="system",
                content=(
                    "Language for this reply: Hindi/Hinglish only. "
                    "Confirm item name + quantity in romanized Hindi. "
                    "Do not answer with empty filler like only 'haan ji'."
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


server = AgentServer()


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

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
        # Wait for a fuller transcript before drafting a reply.
        preemptive_generation=False,
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

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(server)
