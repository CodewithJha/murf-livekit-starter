"""Unit tests for Day 9 agent handoff (no LiveKit cloud / LLM required)."""

from __future__ import annotations

import pytest
from livekit.agents import Agent, ChatContext

from agent import RETURNS_PROMPT, SYSTEM_PROMPT, Assistant, ReturnsRefundsAgent
from catalogue import CatalogueStore
from escalation_store import EscalationStore
from memory_store import MemoryStore


class _FakeRunContext:
    def __init__(self) -> None:
        self._userdata: dict = {}

    @property
    def userdata(self) -> dict:
        return self._userdata


@pytest.mark.asyncio
async def test_transfer_to_returns_hands_off_specialist(tmp_path) -> None:
    store = EscalationStore(
        db_path=tmp_path / "esc.db",
        jsonl_path=tmp_path / "esc.jsonl",
    )
    agent = Assistant(
        memory_store=MemoryStore(tmp_path / "mem.db"),
        catalogue_store=CatalogueStore(),
        escalation_store=store,
        chat_ctx=ChatContext.empty(),
    )

    result = await agent.transfer_to_returns(_FakeRunContext())

    assert isinstance(result, tuple)
    assert len(result) == 2
    specialist, spoken = result
    assert isinstance(specialist, ReturnsRefundsAgent)
    assert isinstance(specialist, Agent)
    assert "returns" in spoken.lower()
    assert hasattr(specialist, "create_escalation")
    assert hasattr(specialist, "transfer_to_dukaan_dost")


@pytest.mark.asyncio
async def test_transfer_to_dukaan_dost_hands_back(tmp_path) -> None:
    store = EscalationStore(
        db_path=tmp_path / "esc.db",
        jsonl_path=tmp_path / "esc.jsonl",
    )
    specialist = ReturnsRefundsAgent(
        chat_ctx=ChatContext.empty(),
        escalation_store=store,
        memory_store=MemoryStore(tmp_path / "mem.db"),
        catalogue_store=CatalogueStore(),
    )

    result = await specialist.transfer_to_dukaan_dost(_FakeRunContext())
    assert isinstance(result, tuple)
    main, spoken = result
    assert isinstance(main, Assistant)
    assert main._resuming is True
    assert "dukaan dost" in spoken.lower()
    assert hasattr(main, "transfer_to_returns")
    assert not hasattr(main, "create_escalation")


def test_main_agent_prompt_routes_disputes_to_handoff() -> None:
    assert "transfer_to_returns" in SYSTEM_PROMPT
    assert "RETURNS HANDOFF" in SYSTEM_PROMPT
    assert "create_escalation" not in SYSTEM_PROMPT
    assert "create_escalation" in RETURNS_PROMPT
    assert "transfer_to_dukaan_dost" in RETURNS_PROMPT


def test_specialist_owns_escalation_tool() -> None:
    main = Assistant()
    specialist = ReturnsRefundsAgent()
    assert hasattr(main, "transfer_to_returns")
    assert not hasattr(main, "create_escalation")
    assert hasattr(specialist, "create_escalation")
    assert hasattr(specialist, "transfer_to_dukaan_dost")
