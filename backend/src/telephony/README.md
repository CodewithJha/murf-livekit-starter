# Telephony — Outbound calls (Day 6)

Dukaan Dost can place **outbound order-confirmation** calls over LiveKit SIP.
This is separate from the browser voice agent (`my-agent`).

## Architecture

1. Run the outbound worker (`agent_name=outbound-agent`).
2. Run `dial.py` — creates a room + dispatches the worker with call metadata.
3. Worker dials via `CreateSIPParticipant` using `LIVEKIT_SIP_OUTBOUND_TRUNK_ID`.
4. On answer, it greets with **who / why / how to opt out**, confirms the order, then hangs up.

## Prerequisites

- LiveKit Cloud project with SIP enabled
- Same `.env.local` keys as the browser agent (`LIVEKIT_*`, `MURF_API_KEY`, `DEEPGRAM_API_KEY`, `GOOGLE_API_KEY`)
- Plus: `LIVEKIT_SIP_OUTBOUND_TRUNK_ID`

## Option A — Linphone (recommended for Day 6)

Official challenge fallback when Twilio trial credits are gone:
[outbound-over-linphone](https://github.com/murf-ai/voice-for-bharat-challenge-2026/blob/main/supplementary/outbound-over-linphone.md)

1. Create a [Linphone account](https://subscribe.linphone.org/register/email) and note `sip:<user>@sip.linphone.org`.
2. Install the Linphone app, sign in, enable mic permission.
3. Settings → Calls → Advanced → turn **Media encryption mandatory** OFF.
4. Prefer **earpiece** over speakerphone when testing — speaker echo can chop the agent voice.
5. In LiveKit Cloud → Telephony → SIP Trunks, create an **outbound** trunk:

```json
{
  "name": "linphone-trunk",
  "address": "sip.linphone.org",
  "transport": "SIP_TRANSPORT_TLS",
  "numbers": ["sip:YOUR_LINPHONE_USERNAME"]
}
```

Or use the sample file:

```bash
# Edit numbers[] first, then:
lk sip outbound create src/telephony/outbound/outbound-trunk.linphone.json
```

5. Copy the trunk id into `backend/.env.local`:

```env
LIVEKIT_SIP_OUTBOUND_TRUNK_ID=ST_xxxxxxxx
```

## Option B — Twilio PSTN

1. Create a Twilio Elastic SIP Trunk (termination URI + credential list + phone number).
2. Fill in [`outbound/outbound-trunk.twilio.json`](outbound/outbound-trunk.twilio.json) and create it:

```bash
lk sip outbound create src/telephony/outbound/outbound-trunk.twilio.json
```

3. Set `LIVEKIT_SIP_OUTBOUND_TRUNK_ID` the same way. Dial with E.164: `--to +9198…`

## Run an order-confirmation call

```bash
cd backend

# Terminal 1 — prefer `start` for phone (cookbook notes `dev` can hit DuplexClosed)
uv run python src/telephony/outbound/agent.py start

# Terminal 2 — Linphone
uv run python src/telephony/outbound/dial.py \
  --to "sip:YOUR_LINPHONE_USER@sip.linphone.org" \
  --name "Priyanshu" \
  --order "two litres milk and one kilo onion" \
  --locale en-IN
```

`dial.py` normalizes full SIP URIs to the **username only** (LiveKit requirement). Prefer:

```bash
uv run python src/telephony/outbound/dial.py --to codewithjha --name Priyanshu --order "two litres milk"
```

```bash
# Hindi greeting
uv run python src/telephony/outbound/dial.py \
  --to "YOUR_LINPHONE_USER" \
  --name "प्रिया" \
  --order "दो लीटर दूध और एक किलो प्याज" \
  --locale hi-IN
```

### Demo script (video)

1. Start recording with Linphone visible.
2. Run `dial.py` — phone rings.
3. Answer — agent says who/why/opt-out.
4. Say “Yes, that’s correct” (or Hindi equivalent).
5. Agent thanks you and hangs up.

Optional: say “stop calling me” to exercise opt-out (saved in Day 4 SQLite memory).

## Tools on the call

| Tool | Purpose |
| ---- | ------- |
| `confirm_order` | Note confirmation / corrections for the shopkeeper |
| `opt_out_of_calls` | Persist `outbound_opt_out` and stop |
| `end_call` | Goodbye + delete room |
| `detected_answering_machine` | Hang up on voicemail |

## Env vars

| Variable | Required | Notes |
| -------- | -------- | ----- |
| `LIVEKIT_SIP_OUTBOUND_TRUNK_ID` | yes | From LiveKit SIP trunk create |
| `OUTBOUND_CUSTOMER_NAME` | no | Default for `--name` |
| `OUTBOUND_ORDER_SUMMARY` | no | Default for `--order` |
| `OUTBOUND_LOCALE` | no | `en-IN` or `hi-IN` |

## Files

```
src/telephony/
├── README.md                 # this file
└── outbound/
    ├── agent.py              # outbound-agent worker
    ├── dial.py               # dispatch + dial trigger
    ├── call_context.py       # metadata + greeting helpers
    ├── outbound-trunk.linphone.json
    └── outbound-trunk.twilio.json
```
