"""Unit tests for Day 4 SQLite caller memory (no LiveKit cloud / LLM required)."""

from __future__ import annotations

import pytest

from agent import Assistant
from memory_store import MemoryStore, normalize_user_id


class _FakeRunContext:
    """Minimal stand-in so memory tools can read/write session userdata."""

    def __init__(self, livekit_identity: str = "") -> None:
        self._userdata = {
            "livekit_identity": livekit_identity,
            "active_user_id": "",
        }

    @property
    def userdata(self) -> dict:
        return self._userdata


def test_normalize_user_id() -> None:
    assert normalize_user_id("Priya") == "priya"
    assert normalize_user_id("  Ramesh Kumar ") == "ramesh-kumar"
    assert normalize_user_id("") == "unknown"


def test_save_and_lookup_by_name(tmp_path) -> None:
    store = MemoryStore(tmp_path / "dukaan_dost.db")
    saved = store.save(
        name="Priya",
        language_preference="hi-IN",
        facts={
            "past_orders": "2L milk, 1kg atta",
            "usual_quantities": "always 2 litres milk",
            "preferred_delivery_slot": "evening 6-8",
        },
        livekit_identity="voice_assistant_user_1",
    )

    assert saved.user_id == "priya"
    assert saved.name == "Priya"
    assert saved.facts["usual_quantities"] == "always 2 litres milk"

    by_name = store.lookup_by_name("priya")
    assert by_name is not None
    assert by_name.facts["preferred_delivery_slot"] == "evening 6-8"

    by_identity = store.lookup_by_identity("voice_assistant_user_1")
    assert by_identity is not None
    assert by_identity.user_id == "priya"


def test_persists_across_store_instances(tmp_path) -> None:
    db = tmp_path / "dukaan_dost.db"
    MemoryStore(db).save(
        name="Ramesh",
        language_preference="en-IN",
        facts={
            "past_orders": "tomatoes 1kg",
            "usual_quantities": "1kg tomatoes",
            "preferred_delivery_slot": "morning",
        },
    )

    again = MemoryStore(db).lookup_by_name("Ramesh")
    assert again is not None
    assert again.facts["past_orders"] == "tomatoes 1kg"
    assert again.last_interaction


def test_merge_facts_on_update(tmp_path) -> None:
    store = MemoryStore(tmp_path / "dukaan_dost.db")
    store.save(
        name="Asha",
        language_preference="en-IN",
        facts={
            "past_orders": "milk",
            "usual_quantities": "1L milk",
            "preferred_delivery_slot": "",
        },
    )
    updated = store.save(
        name="Asha",
        language_preference="hi-IN",
        facts={
            "past_orders": "milk, eggs",
            "usual_quantities": "2L milk",
            "preferred_delivery_slot": "evening",
        },
    )
    assert updated.language_preference == "hi-IN"
    assert updated.facts["past_orders"] == "milk, eggs"
    assert updated.facts["preferred_delivery_slot"] == "evening"


@pytest.mark.asyncio
async def test_save_tool_requires_consent(tmp_path) -> None:
    store = MemoryStore(tmp_path / "dukaan_dost.db")
    agent = Assistant(memory_store=store)
    ctx = _FakeRunContext("test-user")

    declined = await agent.save_caller_memory(
        ctx,
        name="Priya",
        language_preference="en-IN",
        past_orders="2L milk",
        usual_quantities="2L milk",
        preferred_delivery_slot="evening",
        caller_consented=False,
    )

    assert declined["saved"] is False
    assert store.lookup_by_name("Priya") is None


@pytest.mark.asyncio
async def test_save_tool_writes_after_consent(tmp_path) -> None:
    store = MemoryStore(tmp_path / "consent.db")
    agent = Assistant(memory_store=store)
    ctx = _FakeRunContext("id-42")

    result = await agent.save_caller_memory(
        ctx,
        name="Priya",
        language_preference="en-IN",
        past_orders="2L milk, 1kg atta",
        usual_quantities="always 2 litres milk",
        preferred_delivery_slot="evening 6-8",
        caller_consented=True,
    )
    looked = await agent.lookup_caller(ctx, name="Priya")

    assert result["saved"] is True
    assert looked["found"] is True
    assert looked["facts"]["usual_quantities"] == "always 2 litres milk"
    assert looked["livekit_identity"] == "id-42"
    assert ctx.userdata["active_user_id"] == "priya"


@pytest.mark.asyncio
async def test_lookup_by_livekit_identity(tmp_path) -> None:
    store = MemoryStore(tmp_path / "identity.db")
    store.save(
        name="Neha",
        language_preference="hi-IN",
        facts={
            "past_orders": "chai",
            "usual_quantities": "1 packet chai",
            "preferred_delivery_slot": "morning",
        },
        livekit_identity="stable-identity",
    )
    agent = Assistant(memory_store=store)
    looked = await agent.lookup_caller(_FakeRunContext("stable-identity"), name="")
    assert looked["found"] is True
    assert looked["name"] == "Neha"
