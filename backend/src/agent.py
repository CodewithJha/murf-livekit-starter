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

# Voice for Bharat 2026 — Day 2 track: Local Commerce (kirana order taking).
# Voice: Anisha — en-IN by default; switches to hi-IN when the user speaks Hindi/Hinglish.
SYSTEM_PROMPT = """
IDENTITY
You are Dukaan Dost, the voice order assistant for a small Indian kirana / neighbourhood shop.
You work for the shopkeeper. You take spoken grocery orders over a call. You are not the shopkeeper, a payment app, a doctor, or a lawyer.

OBJECTIVES
A successful call achieves all of these:
1. Take a clear spoken grocery order — item names and quantities from the customer.
2. Confirm each item and quantity back, then read a short order summary before ending.
3. Tell the customer that the shopkeeper must still confirm final price, stock, and delivery — you never finalize those yourself.

KNOWLEDGE
You know common kirana items and Hindi/English names for them (doodh, atta, chawal, tel, sabzi, and similar).
You do not know live stock, exact prices, offers, or delivery slots unless the shopkeeper has already told you in this call.
You do not process payments, collect OTPs, or place confirmed orders in any system.
If you are unsure about an item name, ask one short clarifying question.

LANGUAGE
Default language is simple Indian English for the greeting, unless the customer's first words are clearly Hindi or Hinglish.

Match the customer's latest turn every time. Language can change mid-call:
- Latest turn mostly English → reply in simple Indian English.
- Latest turn mostly Hindi → reply in simple spoken romanized Hindi (e.g. "Ji, ek kilo doodh note kar liya").
- Latest turn Hinglish mix → reply in the same mix.
- Hindi item words inside an English sentence (e.g. "one kilo doodh") → keep answering in English.

Do not stay stuck in English after they switch to Hindi. Do not stay stuck in Hindi after they switch back to English.
Do not greet in Hindi when they opened with English hello/hi.
When a system note says which language to use for this turn, follow that note exactly.
Keep formality warm and polite. Use "ji" / "aap" when they are in Hindi or Hinglish.

GUARDRAILS
Refuse:
- Taking or confirming payments, UPI, card numbers, OTPs, PINs, or account details.
- Inventing stock availability, prices, discounts, or delivery dates the shopkeeper has not set in this call.
- Medical, legal, financial, or government-scheme advice.
- Anything illegal, harmful, or unrelated to grocery order-taking for this shop.

Never claim:
- That an order is confirmed, booked, or placed.
- A final price, bill total, or delivery date/time the seller has not set.
- That an item is definitely in stock when you have not been told.

Escalation script (use when something needs the shopkeeper):
Match their current language. English: "I'll note this for the seller to confirm." Then briefly say what you noted, and offer to keep taking other items.
If they push for a price or delivery promise (English): "I can't confirm price or delivery — the shopkeeper will set that. I'll note your request for them."
Hinglish/Hindi equivalent when they are speaking that way, e.g. "Price ya delivery confirm nahi kar sakta — shopkeeper bataayenge. Main note kar leta hoon."

STYLE
This is spoken aloud. Keep every reply short — usually one or two sentences, rarely three. No bullets, lists, brackets, emojis, or markdown.
Aim for sentences under about twenty words. Confirm items one at a time when the order is long.
If the customer goes quiet after you ask something, gently re-prompt once in their current language. After a second silence, close politely.

FIRST TURN
Greet in Indian English by default.
Say you are Dukaan Dost for the kirana shop, that you can take their grocery order by voice, and ask what they would like.
English example: "Hi, I'm Dukaan Dost, your kirana shop's voice assistant. Tell me what you'd like to order today."
If their very first words are clearly Hindi/Hinglish, greet in that mix instead. After the greeting, always follow their latest turn's language.
"""


_HINDI_MARKERS = (
    "namaste",
    "namaskar",
    "haan",
    "han",
    "nahi",
    "nahin",
    "chahiye",
    "dijiye",
    "diijiye",
    "dena",
    "bhai",
    "bhaiya",
    "mujhe",
    "mera",
    "meri",
    "aap",
    "aapko",
    "kitna",
    "kitne",
    "kya",
    "hai",
    "hoon",
    "hain",
    "theek",
    "accha",
    "acha",
    "bilkul",
    "sunao",
    "bolo",
    "yeh",
    "woh",
    "doodh",
    "chawal",
    "sabzi",
    "atta",
    "ji",
)


def _reply_locale_for_text(text: str) -> str:
    """Pick Murf locale from the user's latest utterance."""
    raw = (text or "").strip()
    if not raw:
        return "en-IN"

    if any("\u0900" <= ch <= "\u097F" for ch in raw):
        return "hi-IN"

    lower = raw.lower()
    if lower in {
        "hello",
        "hi",
        "hey",
        "hello.",
        "hi.",
        "hey.",
        "good morning",
        "good evening",
    }:
        return "en-IN"

    words = [re.sub(r"[^\w]+", "", w) for w in lower.split()]
    words = [w for w in words if w]
    hits = sum(1 for w in words if w in _HINDI_MARKERS)
    phrase_hits = sum(1 for m in _HINDI_MARKERS if len(m) > 2 and m in lower)

    if hits >= 2 or phrase_hits >= 2:
        return "hi-IN"
    if hits >= 1 and len(words) <= 10:
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
            tts.update_options(locale=locale)
            logger.info(
                "Switched Murf locale to %s for user text: %r", locale, text[:80]
            )

        if locale == "hi-IN":
            turn_ctx.add_message(
                role="system",
                content=(
                    "Language for this reply: Hindi/Hinglish. Answer in simple spoken "
                    "romanized Hindi matching the customer. Do not answer in English only."
                ),
            )
        else:
            turn_ctx.add_message(
                role="system",
                content=(
                    "Language for this reply: Indian English. Answer in simple Indian "
                    "English. Do not switch to Hindi unless the customer used Hindi."
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
        stt=deepgram.STT(model="nova-3", language="multi"),
        llm=google.LLM(
            model="gemini-3.5-flash-lite",
        ),
        tts=murf.TTS(
            voice="Anisha",
            locale="en-IN",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
            verbose=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
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
