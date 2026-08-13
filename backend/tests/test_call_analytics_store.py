"""Unit tests for Day 8 call analytics (no LiveKit cloud / LLM required)."""

from __future__ import annotations

import json

import pytest

from agent import (
    Assistant,
    finalize_browser_call,
    increment_order_line_count,
)
from call_analytics_store import (
    PII_KEYS,
    CallAnalyticsStore,
    classify_call_outcome,
    utc_now_iso,
)
from catalogue import CatalogueStore
from escalation_store import EscalationStore
from memory_store import MemoryStore


class _FakeRunContext:
    def __init__(self, userdata: dict | None = None) -> None:
        self._userdata = (
            userdata
            if userdata is not None
            else {
                "order_line_count": 0,
                "catalogue_found": False,
                "escalation_created": False,
                "user_turn_count": 0,
                "language": "en-IN",
                "failure_hint": "",
                "call_recorded": False,
            }
        )

    @property
    def userdata(self) -> dict:
        return self._userdata


class _FakeSession:
    def __init__(self, userdata: dict) -> None:
        self.userdata = userdata


def test_classify_order_line_is_success() -> None:
    outcome, failure, reasons = classify_call_outcome(
        order_line_count=1,
        catalogue_found=False,
        escalation_created=False,
        user_turn_count=2,
    )
    assert outcome == "success"
    assert failure == ""
    assert reasons == ["order_line"]


def test_classify_catalogue_hit_is_success() -> None:
    outcome, failure, reasons = classify_call_outcome(
        order_line_count=0,
        catalogue_found=True,
        escalation_created=False,
        user_turn_count=1,
    )
    assert outcome == "success"
    assert failure == ""
    assert reasons == ["catalogue"]


def test_classify_escalation_is_success() -> None:
    outcome, _failure, reasons = classify_call_outcome(
        order_line_count=0,
        catalogue_found=False,
        escalation_created=True,
        user_turn_count=3,
    )
    assert outcome == "success"
    assert reasons == ["escalation"]


def test_classify_greeting_only_is_no_engagement() -> None:
    outcome, failure, reasons = classify_call_outcome(
        order_line_count=0,
        catalogue_found=False,
        escalation_created=False,
        user_turn_count=0,
    )
    assert outcome == "failed"
    assert failure == "no_engagement"
    assert reasons == []


def test_classify_talk_without_markers_is_incomplete() -> None:
    outcome, failure, _reasons = classify_call_outcome(
        order_line_count=0,
        catalogue_found=False,
        escalation_created=False,
        user_turn_count=2,
    )
    assert outcome == "failed"
    assert failure == "incomplete_enquiry"


def test_classify_tool_error_hint() -> None:
    outcome, failure, _reasons = classify_call_outcome(
        order_line_count=0,
        catalogue_found=False,
        escalation_created=False,
        user_turn_count=1,
        failure_hint="tool_error",
    )
    assert outcome == "failed"
    assert failure == "tool_error"


def test_record_writes_sqlite_and_jsonl(tmp_path) -> None:
    db = tmp_path / "dukaan_dost.db"
    jsonl = tmp_path / "calls.jsonl"
    store = CallAnalyticsStore(db_path=db, jsonl_path=jsonl)

    record = store.record(
        call_id="CALL-TEST",
        started_at="2026-08-13T07:00:00+00:00",
        ended_at="2026-08-13T07:01:10+00:00",
        language="en-IN",
        order_line_count=1,
        user_turn_count=2,
    )

    assert record.call_id == "CALL-TEST"
    assert record.outcome == "success"
    assert record.duration_s == 70
    assert record.success_reasons == ["order_line"]
    assert PII_KEYS.isdisjoint(record.to_dict().keys())

    summary = store.summarize()
    assert summary["total"] == 1
    assert summary["successful"] == 1
    assert summary["failed"] == 0
    assert summary["success_rate"] == 100.0

    lines = jsonl.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    mirror = json.loads(lines[0])
    assert mirror["call_id"] == "CALL-TEST"
    assert mirror["outcome"] == "success"
    for key in PII_KEYS:
        assert key not in mirror


def test_record_same_call_id_is_idempotent(tmp_path) -> None:
    store = CallAnalyticsStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "calls.jsonl",
    )
    first = store.record(call_id="CALL-DUP", order_line_count=1, user_turn_count=1)
    second = store.record(call_id="CALL-DUP", order_line_count=9, user_turn_count=9)
    assert first.call_id == second.call_id == "CALL-DUP"
    assert store.summarize()["total"] == 1
    assert store.list_recent()[0].order_line_count == 1


def test_summarize_counts_success_and_failed(tmp_path) -> None:
    store = CallAnalyticsStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "calls.jsonl",
    )
    store.record(call_id="CALL-OK", catalogue_found=True, user_turn_count=1)
    store.record(call_id="CALL-FAIL", user_turn_count=0)

    summary = store.summarize()
    assert summary["total"] == 2
    assert summary["successful"] == 1
    assert summary["failed"] == 1
    assert summary["success_rate"] == 50.0


def test_normal_tools_do_not_auto_insert_call_row(tmp_path) -> None:
    analytics = CallAnalyticsStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "calls.jsonl",
    )
    agent = Assistant(
        memory_store=MemoryStore(tmp_path / "memory.db"),
        catalogue_store=CatalogueStore(),
        escalation_store=EscalationStore(
            db_path=tmp_path / "esc.db",
            jsonl_path=tmp_path / "esc.jsonl",
        ),
        analytics_store=analytics,
    )
    ctx = _FakeRunContext()
    assert increment_order_line_count(ctx) == 1
    assert analytics.summarize()["total"] == 0
    assert hasattr(agent, "note_order_line")
    assert analytics.summarize()["total"] == 0


@pytest.mark.asyncio
async def test_note_order_line_increments_userdata_only(tmp_path) -> None:
    analytics = CallAnalyticsStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "calls.jsonl",
    )
    agent = Assistant(analytics_store=analytics)
    ctx = _FakeRunContext()

    result = await agent.note_order_line(ctx, item_name="milk", quantity=2)
    assert result["noted"] is True
    assert result["order_line_count"] == 1
    assert ctx.userdata["order_line_count"] == 1
    assert analytics.summarize()["total"] == 0


@pytest.mark.asyncio
async def test_lookup_sets_catalogue_found_marker(tmp_path) -> None:
    csv = tmp_path / "zepto_catalogue.csv"
    csv.write_text(
        "Category,name,mrp,discountPercent,availableQuantity,"
        "discountedSellingPrice,weightInGms,outOfStock,quantity\n"
        "Fruits & Vegetables,Onion,2500,16,3,2100,1000,FALSE,1\n",
        encoding="utf-8",
    )
    agent = Assistant(
        catalogue_store=CatalogueStore(csv),
        analytics_store=CallAnalyticsStore(
            db_path=tmp_path / "dukaan_dost.db",
            jsonl_path=tmp_path / "calls.jsonl",
        ),
    )
    ctx = _FakeRunContext()
    result = await agent.lookup_kirana_item(ctx, item_name="onion")
    assert result["found"] is True
    assert ctx.userdata["catalogue_found"] is True


@pytest.mark.asyncio
async def test_escalation_sets_marker_after_consent(tmp_path) -> None:
    analytics = CallAnalyticsStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "calls.jsonl",
    )
    escalations = EscalationStore(
        db_path=tmp_path / "esc.db",
        jsonl_path=tmp_path / "esc.jsonl",
    )
    agent = Assistant(escalation_store=escalations, analytics_store=analytics)
    ctx = _FakeRunContext()
    result = await agent.create_escalation(
        ctx,
        reason="payment_refund_dispute",
        what_happened="Charged twice for milk",
        already_checked="Confirmed item from caller",
        urgency="medium",
        preferred_followup="call back",
        caller_name="Priya",
        language="en-IN",
        caller_consented=True,
    )
    assert result["created"] is True
    assert ctx.userdata["escalation_created"] is True
    assert analytics.summarize()["total"] == 0


@pytest.mark.asyncio
async def test_finalize_records_once_and_classifies_success(tmp_path) -> None:
    store = CallAnalyticsStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "calls.jsonl",
    )
    session = _FakeSession(
        {
            "call_id": "CALL-FIN",
            "call_started_at": utc_now_iso(),
            "order_line_count": 1,
            "catalogue_found": False,
            "escalation_created": False,
            "user_turn_count": 2,
            "language": "hi-IN",
            "failure_hint": "",
            "call_recorded": False,
        }
    )
    first = await finalize_browser_call(session, store)
    second = await finalize_browser_call(session, store)

    assert first is not None
    assert first["call_id"] == "CALL-FIN"
    assert first["outcome"] == "success"
    assert first["language"] == "hi-IN"
    assert second is None
    assert store.summarize()["total"] == 1
    assert store.summarize()["successful"] == 1


@pytest.mark.asyncio
async def test_finalize_greeting_only_is_failed(tmp_path) -> None:
    store = CallAnalyticsStore(
        db_path=tmp_path / "dukaan_dost.db",
        jsonl_path=tmp_path / "calls.jsonl",
    )
    session = _FakeSession(
        {
            "call_id": "CALL-HI",
            "call_started_at": utc_now_iso(),
            "order_line_count": 0,
            "catalogue_found": False,
            "escalation_created": False,
            "user_turn_count": 0,
            "language": "en-IN",
            "failure_hint": "",
            "call_recorded": False,
        }
    )
    result = await finalize_browser_call(session, store)
    assert result is not None
    assert result["outcome"] == "failed"
    assert result["failure_type"] == "no_engagement"
    assert store.summarize()["failed"] == 1
