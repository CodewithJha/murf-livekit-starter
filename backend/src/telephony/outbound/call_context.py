"""Shared outbound call metadata + greeting helpers (no LiveKit imports)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class OutboundCallContext:
    phone_number: str
    customer_name: str
    order_summary: str
    locale: str  # en-IN | hi-IN

    @property
    def display_name(self) -> str:
        return self.customer_name.strip() or "ji"


def normalize_sip_call_to(target: str) -> str:
    """LiveKit SipCallTo wants a phone number or SIP user — not a full SIP URI.

    Examples:
      sip:codewithjha@sip.linphone.org → codewithjha
      codewithjha@sip.linphone.org → codewithjha
      +919876543210 → +919876543210
      codewithjha → codewithjha
    """
    value = (target or "").strip()
    if not value:
        return value
    # Strip sip: / sips: prefix
    lower = value.lower()
    if lower.startswith("sips:"):
        value = value[5:]
    elif lower.startswith("sip:"):
        value = value[4:]
    # Drop domain / params if present (user@host;params)
    if "@" in value:
        value = value.split("@", 1)[0]
    if ";" in value:
        value = value.split(";", 1)[0]
    return value.strip()


def parse_job_metadata(metadata: str | None) -> dict[str, Any]:
    """Parse dispatch metadata. Accepts JSON object or bare phone/SIP target."""
    if not metadata or not str(metadata).strip():
        return {}
    raw = str(metadata).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"phone_number": raw}
    if isinstance(data, dict):
        return data
    return {"phone_number": raw}


def call_context_from_metadata(
    metadata: str | None,
    *,
    default_name: str | None = None,
    default_order: str | None = None,
    default_locale: str | None = None,
) -> OutboundCallContext | None:
    data = parse_job_metadata(metadata)
    phone = str(data.get("phone_number") or data.get("to") or "").strip()
    if not phone:
        return None
    phone = normalize_sip_call_to(phone)

    name = str(
        data.get("customer_name")
        or data.get("name")
        or default_name
        or os.getenv("OUTBOUND_CUSTOMER_NAME")
        or ""
    ).strip()
    order = str(
        data.get("order_summary")
        or data.get("order")
        or default_order
        or os.getenv("OUTBOUND_ORDER_SUMMARY")
        or "your grocery order"
    ).strip()
    locale = str(
        data.get("locale") or default_locale or os.getenv("OUTBOUND_LOCALE") or "en-IN"
    ).strip()
    if locale not in {"en-IN", "hi-IN"}:
        locale = "en-IN"

    return OutboundCallContext(
        phone_number=phone,
        customer_name=name,
        order_summary=order or "your grocery order",
        locale=locale,
    )


def build_greeting(ctx: OutboundCallContext) -> str:
    """Opening: who, why, opt-out, then invite a short confirmation."""
    name = ctx.display_name
    order = ctx.order_summary
    if ctx.locale == "hi-IN":
        return (
            f"नमस्ते {name}, मैं दूकान दोस्त हूँ, आपके किराना शॉप से बोल रहा हूँ। "
            f"आज आपके ऑर्डर की पुष्टि के लिए कॉल किया है — {order}। "
            f"अगर आप ये कॉल नहीं चाहते, तो बस बोलिए मुझे कॉल मत करो। "
            f"वरना बताइए, क्या ये ऑर्डर सही है, या कुछ बदलना है?"
        )

    return (
        f"Hi {name}, this is Dukaan Dost calling from your kirana shop. "
        f"I'm ringing to quickly confirm today's order — {order}. "
        f"If you don't want these calls, just say stop calling me. "
        f"Otherwise, is this order correct, or would you like to change anything?"
    )


def build_system_prompt(ctx: OutboundCallContext) -> str:
    name = ctx.display_name
    order = ctx.order_summary
    locale_line = (
        "Reply in simple Hindi using Devanagari script only."
        if ctx.locale == "hi-IN"
        else "Reply in simple Indian English."
    )
    return f"""
IDENTITY
You are Dukaan Dost placing an OUTBOUND phone call for a small Indian kirana shop.
The customer did not dial you — you called them.

CALL CONTEXT
- Customer name: {name}
- Order to confirm: {order}
- Locale for this call: {ctx.locale}

OPENING (already spoken or about to be spoken)
You must open with who you are, why you called, and how to opt out.
Do not skip the opt-out line on the first turn.

OBJECTIVES
1. Confirm whether today's order is correct ({order}).
2. If they correct items or quantities, repeat the updated list clearly and ask once if that is final.
3. When they confirm, thank them warmly in two short sentences (mention you will note it for the shopkeeper), then use end_call.
4. If they say stop calling / don't call / opt out, use opt_out_of_calls then end_call.
5. If you hear a voicemail or answering machine, use detected_answering_machine immediately.

TOOLS
- confirm_order: when they confirm or give corrections (pass confirmed=true/false and final_order text).
- opt_out_of_calls: when they ask to stop receiving these calls.
- end_call: after goodbye, once the conversation is finished.
- detected_answering_machine: hang up on voicemail.

GUARDRAILS
Never invent prices, delivery times, or payment details.
Never take OTPs, card numbers, or UPI PINs.
You are not the shopkeeper — final bill stays with the shop.
Keep replies to two or three short spoken sentences. No markdown or emojis.
{locale_line}
""".strip()
