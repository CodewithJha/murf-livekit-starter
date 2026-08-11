"""Unit tests for Day 6 outbound metadata and opening disclosure (offline)."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from telephony.outbound.call_context import (  # noqa: E402
    OutboundCallContext,
    build_greeting,
    build_system_prompt,
    call_context_from_metadata,
    parse_job_metadata,
)


def test_parse_json_metadata() -> None:
    data = parse_job_metadata(
        '{"phone_number":"sip:u@sip.linphone.org","customer_name":"Priya",'
        '"order_summary":"two litres milk","locale":"en-IN"}'
    )
    assert data["phone_number"] == "sip:u@sip.linphone.org"
    assert data["customer_name"] == "Priya"


def test_parse_bare_phone_metadata() -> None:
    data = parse_job_metadata("+919876543210")
    assert data["phone_number"] == "+919876543210"


def test_call_context_requires_phone() -> None:
    assert call_context_from_metadata("{}") is None
    assert call_context_from_metadata(None) is None


def test_call_context_from_metadata() -> None:
    ctx = call_context_from_metadata(
        '{"phone_number":"+91111","name":"Ravi","order":"1kg atta","locale":"hi-IN"}'
    )
    assert ctx is not None
    assert ctx.phone_number == "+91111"
    assert ctx.customer_name == "Ravi"
    assert ctx.order_summary == "1kg atta"
    assert ctx.locale == "hi-IN"


def test_english_greeting_has_who_why_opt_out() -> None:
    ctx = OutboundCallContext(
        phone_number="sip:u@sip.linphone.org",
        customer_name="Priya",
        order_summary="two litres milk and one kilo onion",
        locale="en-IN",
    )
    greeting = build_greeting(ctx).lower()
    assert "dukaan dost" in greeting
    assert "kirana" in greeting
    assert "confirm" in greeting
    assert "milk" in greeting and "onion" in greeting
    assert "stop calling" in greeting


def test_hindi_greeting_has_who_why_opt_out() -> None:
    ctx = OutboundCallContext(
        phone_number="sip:u@sip.linphone.org",
        customer_name="प्रिया",
        order_summary="दो लीटर दूध",
        locale="hi-IN",
    )
    greeting = build_greeting(ctx)
    assert "दूकान दोस्त" in greeting
    assert "किराना" in greeting
    assert "दो लीटर दूध" in greeting
    assert "कॉल मत करो" in greeting


def test_normalize_sip_call_to() -> None:
    from telephony.outbound.call_context import normalize_sip_call_to

    assert normalize_sip_call_to("sip:codewithjha@sip.linphone.org") == "codewithjha"
    assert normalize_sip_call_to("codewithjha@sip.linphone.org") == "codewithjha"
    assert normalize_sip_call_to("codewithjha") == "codewithjha"
    assert normalize_sip_call_to("+919876543210") == "+919876543210"


def test_system_prompt_includes_context_and_guardrails() -> None:
    ctx = OutboundCallContext(
        phone_number="+91111",
        customer_name="Priya",
        order_summary="eggs and bread",
        locale="en-IN",
    )
    prompt = build_system_prompt(ctx).lower()
    assert "priya" in prompt
    assert "eggs and bread" in prompt
    assert "opt out" in prompt or "opt-out" in prompt
    assert "end_call" in prompt
    assert "never invent prices" in prompt or "never invent" in prompt
