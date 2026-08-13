"""SQLite + JSONL persistence for Dukaan Dost call analytics (Day 8)."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

VALID_LANGUAGES = frozenset({"en-IN", "hi-IN"})
VALID_OUTCOMES = frozenset({"success", "failed"})
VALID_FAILURE_TYPES = frozenset(
    {"", "incomplete_enquiry", "no_engagement", "tool_error"}
)
VALID_CHANNELS = frozenset({"browser"})

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "dukaan_dost.db"
DEFAULT_JSONL_PATH = Path(__file__).resolve().parent.parent / "data" / "calls.jsonl"

PII_KEYS = frozenset(
    {
        "transcript",
        "name",
        "caller_name",
        "identity",
        "livekit_identity",
        "phone",
        "otp",
        "pin",
        "card",
    }
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_call_id() -> str:
    return f"CALL-{secrets.token_hex(2).upper()}"


def _parse_iso(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_seconds(started_at: str, ended_at: str) -> int:
    start = _parse_iso(started_at)
    end = _parse_iso(ended_at)
    if start is None or end is None:
        return 0
    return max(0, int((end - start).total_seconds()))


def classify_call_outcome(
    *,
    order_line_count: int,
    catalogue_found: bool,
    escalation_created: bool,
    user_turn_count: int,
    failure_hint: str = "",
) -> tuple[str, str, list[str]]:
    """Return (outcome, failure_type, success_reasons)."""
    reasons: list[str] = []
    if int(order_line_count or 0) > 0:
        reasons.append("order_line")
    if catalogue_found:
        reasons.append("catalogue")
    if escalation_created:
        reasons.append("escalation")
    if reasons:
        return "success", "", reasons

    hint = (failure_hint or "").strip()
    if hint == "tool_error":
        return "failed", "tool_error", []
    if int(user_turn_count or 0) > 0:
        return "failed", "incomplete_enquiry", []
    return "failed", "no_engagement", []


@dataclass
class CallRecord:
    call_id: str
    started_at: str
    ended_at: str
    duration_s: int
    channel: str
    language: str
    outcome: str
    failure_type: str
    order_line_count: int
    catalogue_found: bool
    escalation_created: bool
    success_reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_s": self.duration_s,
            "channel": self.channel,
            "language": self.language,
            "outcome": self.outcome,
            "failure_type": self.failure_type,
            "order_line_count": self.order_line_count,
            "catalogue_found": self.catalogue_found,
            "escalation_created": self.escalation_created,
            "success_reasons": list(self.success_reasons),
        }


class CallAnalyticsStore:
    """Thread-safe SQLite store with append-only JSONL mirror for the dashboard."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        jsonl_path: Path | str | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        self.jsonl_path = (
            Path(jsonl_path) if jsonl_path is not None else DEFAULT_JSONL_PATH
        )
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if str(self.jsonl_path) != ":memory:":
            self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._memory_conn: sqlite3.Connection | None = None
        if str(self.db_path) == ":memory:":
            self._memory_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_conn.row_factory = sqlite3.Row
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_conn is not None:
            return self._memory_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calls (
                    call_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    duration_s INTEGER NOT NULL DEFAULT 0,
                    channel TEXT NOT NULL DEFAULT 'browser',
                    language TEXT NOT NULL DEFAULT 'en-IN',
                    outcome TEXT NOT NULL,
                    failure_type TEXT NOT NULL DEFAULT '',
                    order_line_count INTEGER NOT NULL DEFAULT 0,
                    catalogue_found INTEGER NOT NULL DEFAULT 0,
                    escalation_created INTEGER NOT NULL DEFAULT 0,
                    success_reasons TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_calls_started ON calls(started_at DESC)"
            )
            conn.commit()

    def _row_to_record(self, row: sqlite3.Row) -> CallRecord:
        try:
            reasons = json.loads(row["success_reasons"] or "[]")
        except json.JSONDecodeError:
            reasons = []
        if not isinstance(reasons, list):
            reasons = []
        return CallRecord(
            call_id=row["call_id"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            duration_s=int(row["duration_s"] or 0),
            channel=row["channel"] or "browser",
            language=row["language"] or "en-IN",
            outcome=row["outcome"],
            failure_type=row["failure_type"] or "",
            order_line_count=int(row["order_line_count"] or 0),
            catalogue_found=bool(row["catalogue_found"]),
            escalation_created=bool(row["escalation_created"]),
            success_reasons=[str(r) for r in reasons],
        )

    def _append_jsonl(self, record: dict[str, Any]) -> None:
        if str(self.jsonl_path) == ":memory:":
            return
        line = json.dumps(record, ensure_ascii=False)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _lookup(self, conn: sqlite3.Connection, call_id: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM calls WHERE call_id = ?",
            (call_id,),
        ).fetchone()

    def _unique_call_id(self, conn: sqlite3.Connection) -> str:
        for _ in range(8):
            call_id = new_call_id()
            if self._lookup(conn, call_id) is None:
                return call_id
        raise RuntimeError("Could not allocate a unique call id")

    def record(
        self,
        *,
        call_id: str | None = None,
        started_at: str | None = None,
        ended_at: str | None = None,
        channel: str = "browser",
        language: str = "en-IN",
        order_line_count: int = 0,
        catalogue_found: bool = False,
        escalation_created: bool = False,
        user_turn_count: int = 0,
        failure_hint: str = "",
    ) -> CallRecord:
        ended = (ended_at or "").strip() or utc_now_iso()
        started = (started_at or "").strip() or ended
        lang = (language or "en-IN").strip() or "en-IN"
        if lang not in VALID_LANGUAGES:
            lang = "en-IN"
        chan = (channel or "browser").strip() or "browser"
        if chan not in VALID_CHANNELS:
            chan = "browser"

        outcome, failure_type, reasons = classify_call_outcome(
            order_line_count=order_line_count,
            catalogue_found=catalogue_found,
            escalation_created=escalation_created,
            user_turn_count=user_turn_count,
            failure_hint=failure_hint,
        )
        duration_s = duration_seconds(started, ended)
        reasons_json = json.dumps(reasons, ensure_ascii=False)

        with self._lock:
            conn = self._connect()
            requested = (call_id or "").strip()
            if requested:
                existing = self._lookup(conn, requested)
                if existing is not None:
                    return self._row_to_record(existing)
                cid = requested
            else:
                cid = self._unique_call_id(conn)

            conn.execute(
                """
                INSERT INTO calls (
                    call_id, started_at, ended_at, duration_s, channel, language,
                    outcome, failure_type, order_line_count, catalogue_found,
                    escalation_created, success_reasons
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    started,
                    ended,
                    duration_s,
                    chan,
                    lang,
                    outcome,
                    failure_type,
                    int(order_line_count or 0),
                    1 if catalogue_found else 0,
                    1 if escalation_created else 0,
                    reasons_json,
                ),
            )
            conn.commit()
            row = self._lookup(conn, cid)

        assert row is not None
        record = self._row_to_record(row)
        payload = record.to_dict()
        assert PII_KEYS.isdisjoint(payload.keys())
        self._append_jsonl(payload)
        return record

    def summarize(self) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            total = int(conn.execute("SELECT COUNT(*) FROM calls").fetchone()[0])
            successful = int(
                conn.execute(
                    "SELECT COUNT(*) FROM calls WHERE outcome = 'success'"
                ).fetchone()[0]
            )
            failed = int(
                conn.execute(
                    "SELECT COUNT(*) FROM calls WHERE outcome = 'failed'"
                ).fetchone()[0]
            )
        rate = round(100.0 * successful / total, 1) if total else 0.0
        return {
            "total": total,
            "successful": successful,
            "failed": failed,
            "success_rate": rate,
        }

    def list_recent(self, limit: int = 20) -> list[CallRecord]:
        cap = max(1, min(int(limit or 20), 100))
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                """
                SELECT * FROM calls
                ORDER BY started_at DESC, call_id DESC
                LIMIT ?
                """,
                (cap,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]
