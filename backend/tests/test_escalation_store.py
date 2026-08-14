"""Unit tests for Day 7 human-help escalations (no LiveKit cloud / LLM required)."""

from __future__ import annotations

import json

import pytest

from agent import Assistant, ReturnsRefundsAgent
from catalogue import CatalogueStore
from escalation_store import EscalationStore, sanitize_summary_text
from memory_store import MemoryStore


class _FakeRunContext:
    def __init__(self) -> None:
        self._userdata: dict = {}

    @property
    def userdata(self) -> dict:
        return self._userdata


def test_sanitize_strips_otp_and_card_patterns() -> None:
    raw = "Customer says OTP is 482910 and card 4111 1111 1111 1111 was charged twice"
    cleaned = sanitize_summary_text(raw)
    assert "482910" not in cleaned
    assert "4111" not in cleaned
    assert "[redacted]" in cleaned


def test_create_requires_consent(tmp_path) -> None:
    db = tmp_path / "dukaan_dost.db"
    jsonl = tmp_path / "escalations.jsonl"
    store = EscalationStore(db_path=db, jsonl_path=jsonl)

    result = store.create(
        reason="payment_refund_dispute",
        what_happened="Charged twice for milk order",
        already_checked="Noted order from memory",
        urgency="medium",
        preferred_followup="call back",
        caller_name="Priya",
        language="en-IN",
        caller_consented=False,
    )

    assert result["created"] is False
    assert result["reference_id"] == ""
    assert store.list_open() == []
    assert not jsonl.exists()


def test_create_with_consent_writes_sqlite_and_jsonl(tmp_path) -> None:
    db = tmp_path / "dukaan_dost.db"
    jsonl = tmp_path / "escalations.jsonl"
    store = EscalationStore(db_path=db, jsonl_path=jsonl)

    result = store.create(
        reason="order_dispute",
        what_happened="Received damaged tomatoes in yesterday delivery",
        already_checked="Looked up catalogue; no prior order on file",
        urgency="high",
        preferred_followup="WhatsApp",
        caller_name="Ramesh",
        language="hi-IN",
        caller_consented=True,
    )

    assert result["created"] is True
    assert result["reference_id"].startswith("ESC-")

    open_rows = store.list_open()
    assert len(open_rows) == 1
    assert open_rows[0].reference_id == result["reference_id"]
    assert open_rows[0].reason == "order_dispute"
    assert open_rows[0].caller_name == "Ramesh"

    lines = jsonl.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    mirror = json.loads(lines[0])
    assert mirror["reference_id"] == result["reference_id"]
    assert mirror["status"] == "open"


def test_persists_across_store_instances(tmp_path) -> None:
    db = tmp_path / "dukaan_dost.db"
    jsonl = tmp_path / "escalations.jsonl"
    first = EscalationStore(db_path=db, jsonl_path=jsonl)
    created = first.create(
        reason="payment_refund_dispute",
        what_happened="UPI payment failed but amount deducted",
        already_checked="Asked for transaction time only",
        urgency="medium",
        preferred_followup="in-shop",
        caller_name="Asha",
        language="en-IN",
        caller_consented=True,
    )

    again = EscalationStore(db_path=db, jsonl_path=jsonl)
    rows = again.list_open()
    assert len(rows) == 1
    assert rows[0].reference_id == created["reference_id"]


@pytest.mark.asyncio
async def test_create_escalation_tool_requires_consent(tmp_path) -> None:
    store = EscalationStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "escalations.jsonl",
    )
    agent = ReturnsRefundsAgent(escalation_store=store)
    ctx = _FakeRunContext()

    result = await agent.create_escalation(
        ctx,
        reason="payment_refund_dispute",
        what_happened="Double charged for milk",
        already_checked="Confirmed item from caller",
        urgency="medium",
        preferred_followup="call back",
        caller_name="Priya",
        language="en-IN",
        caller_consented=False,
    )

    assert result["created"] is False
    assert store.list_open() == []


@pytest.mark.asyncio
async def test_create_escalation_tool_writes_after_consent(tmp_path) -> None:
    store = EscalationStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "escalations.jsonl",
    )
    agent = ReturnsRefundsAgent(escalation_store=store)
    ctx = _FakeRunContext()

    result = await agent.create_escalation(
        ctx,
        reason="order_dispute",
        what_happened="Missing one kilo onion from delivery",
        already_checked="Repeated order summary to caller",
        urgency="low",
        preferred_followup="call back tomorrow",
        caller_name="Neha",
        language="en-IN",
        caller_consented=True,
    )

    assert result["created"] is True
    assert result["reference_id"].startswith("ESC-")
    assert store.list_open()[0].caller_name == "Neha"


def test_normal_order_path_does_not_auto_create_escalation(tmp_path) -> None:
    """Escalations exist only when create_escalation is called — not on catalogue lookup."""
    store = EscalationStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "escalations.jsonl",
    )
    memory = MemoryStore(tmp_path / "dukaan_dost.db")
    agent = Assistant(
        memory_store=memory,
        catalogue_store=CatalogueStore(),
        escalation_store=store,
    )
    specialist = ReturnsRefundsAgent(escalation_store=store)

    assert agent._escalations.list_open() == []
    assert hasattr(agent, "lookup_kirana_item")
    assert hasattr(agent, "transfer_to_returns")
    assert not hasattr(agent, "create_escalation")
    assert hasattr(specialist, "create_escalation")
    assert agent._escalations.list_open() == []
