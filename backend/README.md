# Backend — Voice Agent with Murf Falcon TTS

The Python backend for the Voice Agent Starter. It runs a real-time voice AI pipeline using [LiveKit Agents](https://docs.livekit.io/agents), connecting Murf Falcon TTS, Deepgram STT, and Google Gemini into a single conversational agent.

## How It Works

```
User speaks → [Deepgram STT] → text → [Gemini LLM] → response → [Murf Falcon TTS] → audio → User hears
```

LiveKit handles the real-time audio transport. The agent connects to LiveKit as a participant, listens for user speech, and responds with synthesized audio.

## Setup

### 1. Install dependencies

```bash
cd backend
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env.local
```

Fill in your keys in `.env.local`:

| Variable             | Where to get it                                           |
| -------------------- | --------------------------------------------------------- |
| `LIVEKIT_URL`        | [LiveKit Cloud](https://cloud.livekit.io/) → Settings     |
| `LIVEKIT_API_KEY`    | [LiveKit Cloud](https://cloud.livekit.io/) → Settings     |
| `LIVEKIT_API_SECRET` | [LiveKit Cloud](https://cloud.livekit.io/) → Settings     |
| `MURF_API_KEY`       | [murf.ai/api/dashboard](https://murf.ai/api/dashboard)    |
| `DEEPGRAM_API_KEY`   | [deepgram.com](https://console.deepgram.com/)             |
| `GOOGLE_API_KEY`     | [aistudio.google.com](https://aistudio.google.com/apikey) |

For LiveKit Cloud users, you can auto-populate LiveKit credentials:

```bash
lk cloud auth
lk app env -w -d .env.local
```

### 3. Download models

```bash
uv run python src/agent.py download-files
```

This downloads Silero VAD and the LiveKit turn detector models.

### 4. Run the agent

```bash
# Development mode (auto-reload)
uv run python src/agent.py dev

# Or test directly in your terminal (no frontend needed)
uv run python src/agent.py console

# Production
uv run python src/agent.py start
```

## Configuration

All configuration lives in [`src/agent.py`](src/agent.py).

### System prompt

The `SYSTEM_PROMPT` constant at the top of `agent.py` controls what your agent does. Change it to build any voice-powered use case.

#### Example prompts

**Customer Support (default):**

```
You are a friendly and efficient customer support agent for a tech company. Help users with account issues, billing questions, and product troubleshooting. Be concise, empathetic, and solution-oriented. If you don't know something, say so honestly and offer to escalate.
```

**Language Tutor:**

```
You are a patient and encouraging language tutor helping the user practice conversational Spanish. Speak primarily in Spanish but switch to English to explain grammar or vocabulary when needed. Correct mistakes gently and suggest better phrasing. Keep conversations natural and fun.
```

**AI Receptionist:**

```
You are a professional receptionist for a medical clinic. Help callers schedule appointments, answer questions about office hours and services, and take messages for doctors. Be warm but efficient. Ask for the caller's name and reason for calling upfront.
```

**Interview Coach:**

```
You are an experienced interview coach. Conduct mock interviews with the user for software engineering roles. Ask one behavioral or technical question at a time, let the user answer fully, then give specific feedback on their response — what was strong, what could improve, and a suggested reframe. Keep the tone encouraging but honest.
```

**Sales Assistant:**

```
You are a knowledgeable sales assistant for an electronics store. Help customers find the right product by asking about their needs, budget, and preferences. Compare options clearly, highlight trade-offs, and make a recommendation. Never be pushy — focus on helping the customer make the best decision for them.
```

**Fitness Coach:**

```
You are an upbeat personal fitness coach. Help users plan workouts, suggest exercises for specific muscle groups, and answer questions about form and technique. Ask about their fitness level and any injuries before recommending exercises. Keep instructions clear and motivating.
```

**Storyteller / Bedtime Narrator:**

```
You are a creative storyteller who tells original bedtime stories for children aged 4–8. Ask the child (or parent) for a character name, a favorite animal, and a setting, then weave a short, calming story. Use vivid but simple language. End each story on a peaceful, sleepy note.
```

**Meeting Summarizer:**

```
You are a meeting assistant. The user will describe what happened in a meeting or read you their notes. Summarize the key decisions, action items (with owners if mentioned), and any open questions. Be concise and structured. Ask clarifying questions if something is ambiguous.
```

**Trivia Game Host:**

```
You are an enthusiastic trivia game host. Ask the user one trivia question at a time from a mix of categories — science, history, pop culture, geography, and sports. Wait for their answer, tell them if they're right or wrong, give a brief fun fact, then move to the next question. Keep score and announce it every 5 questions.
```

**Mental Health Check-in Companion:**

```
You are a gentle, non-clinical wellness companion. Help users talk through their day, reflect on how they're feeling, and practice simple grounding exercises like deep breathing or gratitude lists. You are not a therapist — if the user expresses serious distress or mentions self-harm, gently encourage them to reach out to a professional or crisis helpline.
```

### Voice

Set the `voice` argument in the `murf.TTS(...)` call:

```python
tts=murf.TTS(
    voice="en-US-matthew",    # Change this
    style="Conversation",
    tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
    text_pacing=True
)
```

Some voice options:

| Voice ID | Description                      |
| -------- | -------------------------------- |
| `Anisha` | Indian English, female (default) |
| `Amara`  | US English, female               |
| `Hazel`  | UK English, female               |
| `Gordon` | US English, male                 |

Browse all 150+ voices: [Murf Voice Library](https://murf.ai/api/docs/voices-styles/voice-library).

### STT (Speech-to-Text)

Default is Deepgram Nova-3. Change in the `AgentSession(stt=...)` call:

```python
stt=deepgram.STT(model="nova-3")
```

### LLM

Default is Google Gemini. To switch:

- **Gemini (default):** Set `GOOGLE_API_KEY` in `.env.local`
- **OpenAI:** Set `OPENAI_API_KEY`, install `livekit-agents[openai]`, and change the `llm=` argument

## Testing

The project includes an eval suite based on the LiveKit Agents [testing framework](https://docs.livekit.io/agents/build/testing/):

```bash
uv run pytest
```

- [`tests/test_agent.py`](tests/test_agent.py) — LLM-as-judge evals (needs LiveKit credentials)
- [`tests/test_memory_store.py`](tests/test_memory_store.py) — Day 4 SQLite memory (offline)
- [`tests/test_catalogue.py`](tests/test_catalogue.py) — Day 5 catalogue lookup (offline)
- [`tests/test_outbound_context.py`](tests/test_outbound_context.py) — Day 6 greeting / metadata (offline)
- [`tests/test_escalation_store.py`](tests/test_escalation_store.py) — Day 7 human-help escalations (offline)
- [`tests/test_call_analytics_store.py`](tests/test_call_analytics_store.py) — Day 8 call analytics (offline)
- [`tests/test_handoff.py`](tests/test_handoff.py) — Day 9 returns specialist handoff (offline)

To run LiveKit evals in CI, add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` as repository secrets.

## Day 5 — Catalogue tool

`lookup_kirana_item` searches a **local CSV**, not a live store API.

| Path | Source |
| ---- | ------ |
| [`data/zepto_catalogue.csv`](data/zepto_catalogue.csv) | Public scraped Zepto-style inventory ([zepto_v2.csv](https://raw.githubusercontent.com/amlanmohanty1/zepto-SQL-data-analysis-project/main/zepto_v2.csv)) |

Money columns in the CSV are in **paise**; the agent converts to rupees for speech. Prices and stock are **indicative** — the prompt still defers the final bill to the shopkeeper. If the file is missing, the tool returns a graceful error and the agent must not invent numbers.

Loader: [`src/catalogue.py`](src/catalogue.py).

## Day 6 — Outbound order confirmation

The browser agent stays inbound. Outbound uses a **second worker** (`outbound-agent`) over LiveKit SIP (Linphone recommended; Twilio optional).

Full setup: [`src/telephony/README.md`](src/telephony/README.md).

```bash
# Terminal 1
uv run python src/telephony/outbound/agent.py start

# Terminal 2
uv run python src/telephony/outbound/dial.py \
  --to "sip:YOUR_LINPHONE_USER@sip.linphone.org" \
  --name "Priyanshu" \
  --order "two litres milk and one kilo onion"
```

Requires `LIVEKIT_SIP_OUTBOUND_TRUNK_ID` in `.env.local`. Opening line states who is calling, why, and how to opt out.

## Day 7 — Human help escalations

Browser agent only (no SIP). When a caller has a **payment/refund dispute** or **order dispute**, Dukaan Dost hands off to the **returns specialist** (Day 9), who can call `create_escalation` after explicit consent.

| Storage | Path |
| ------- | ---- |
| SQLite | [`data/dukaan_dost.db`](data/dukaan_dost.db) — `escalations` table |
| JSONL mirror | [`data/escalations.jsonl`](data/escalations.jsonl) — append-only for the shopkeeper UI |

The tool returns a reference ID (`ESC-…`) and an honest next step (shopkeeper will review; no instant callback promised). Summaries are sanitized — OTP/PIN/card-like strings are redacted before write.

Shopkeeper view: frontend [`/escalations`](http://127.0.0.1:3001/escalations) reads the JSONL via [`frontend/app/api/escalations/route.ts`](../frontend/app/api/escalations/route.ts).

Loader: [`src/escalation_store.py`](src/escalation_store.py).

## Day 8 — Call analytics dashboard

Browser agent only (no SIP). Every LiveKit session writes one row when the call ends.

**Success** means at least one of: an order line was noted (`note_order_line`), the catalogue found a product, or a human-help escalation was created. Otherwise the call is **failed** (incomplete enquiry or no engagement). Failed does not mean the app crashed.

| Storage | Path |
| ------- | ---- |
| SQLite | [`data/dukaan_dost.db`](data/dukaan_dost.db) — `calls` table |
| JSONL mirror | [`data/calls.jsonl`](data/calls.jsonl) — append-only for the dashboard |

Rows store outcome, duration, channel, language, and success flags only — **no names, identities, or transcripts**. No new secrets required.

Dashboard: frontend [`/analytics`](http://127.0.0.1:3001/analytics) reads the JSONL via [`frontend/app/api/analytics/route.ts`](../frontend/app/api/analytics/route.ts). It shows total / successful / failed calls plus success rate.

Loader: [`src/call_analytics_store.py`](src/call_analytics_store.py).

## Day 9 — Returns specialist handoff

Browser agent only. Dukaan Dost (Anisha) takes grocery orders. For payment/refund or past-order disputes it calls `transfer_to_returns`, which LiveKit switches to **`ReturnsRefundsAgent`** (Murf **Pooja** voice) with prior chat context copied (`exclude_instructions=True`).

The specialist introduces itself, continues the dispute, and may create a shopkeeper ticket via `create_escalation` (Day 7). If the caller wants a new grocery order, it calls `transfer_to_dukaan_dost` to hand back.

| Stay with Dukaan Dost | Hand off to returns |
| --------------------- | ------------------- |
| “Two litres milk” | “I was charged twice / I want a refund” |
| Stock / price questions | Wrong, missing, or damaged past order |

No new secrets. Same room — handoff is an in-session agent swap, not a second worker.

## Deployment

### Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/tIVCF1?referralCode=cNjn2P&utm_medium=integration&utm_source=template&utm_campaign=generic)

Set these environment variables in Railway:

- `MURF_API_KEY`
- `DEEPGRAM_API_KEY`
- `GOOGLE_API_KEY`
- `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`

### Docker

A production-ready [Dockerfile](Dockerfile) is included:

```bash
docker build -t murf-voice-agent .
docker run --env-file .env.local murf-voice-agent
```

## Project Structure

```
backend/
├── src/
│   ├── agent.py          # Browser agent — pipeline, prompt, tools
│   ├── memory_store.py   # Day 4 SQLite caller memory
│   ├── catalogue.py      # Day 5 CSV catalogue lookup
│   ├── escalation_store.py  # Day 7 human-help escalations
│   ├── call_analytics_store.py  # Day 8 call analytics
│   └── telephony/        # Day 6 outbound SIP calls
│       ├── README.md
│       └── outbound/
│           ├── agent.py
│           ├── dial.py
│           └── call_context.py
├── data/
│   ├── .gitkeep
│   └── zepto_catalogue.csv   # Public scraped inventory (not a live API)
├── tests/
│   ├── test_agent.py
│   ├── test_memory_store.py
│   ├── test_catalogue.py
│   ├── test_outbound_context.py
│   ├── test_escalation_store.py
│   ├── test_call_analytics_store.py
│   └── test_handoff.py
├── .env.example
├── pyproject.toml
├── Dockerfile
└── railway.toml
```

## Links

- [Murf Falcon TTS Docs](https://murf.ai/api/docs/text-to-speech/streaming)
- [Murf Voice Library](https://murf.ai/api/docs/voices-styles/voice-library)
- [LiveKit Agents Docs](https://docs.livekit.io/agents)
- [Deepgram Nova-3 Docs](https://developers.deepgram.com)

## License

MIT — see [LICENSE](LICENSE).
