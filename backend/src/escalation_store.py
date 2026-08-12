"""SQLite + JSONL persistence for Dukaan Dost human-help escalations (Day 7)."""

from __future__ import annotations

import json
import re
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

Reason = Literal["payment_refund_dispute", "order_dispute"]
Urgency = Literal["low", "medium", "high"]
Language = Literal["en-IN", "hi-IN"]
Status = Literal["open", "resolved"]

VALID_REASONS = frozenset({"payment_refund_dispute", "order_dispute"})
VALID_URGENCIES = frozenset({"low", "medium", "high"})
VALID_LANGUAGES = frozenset({"en-IN", "hi-IN"})

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "dukaan_dost.db"
DEFAULT_JSONL_PATH = Path(__file__).resolve().parent.parent / "data" / "escalations.jsonl"

# Obvious secret patterns — redact before persisting summaries.
_OTP_PATTERN = re.compile(
    r"\b(?:otp|one[- ]time|verification)\s*(?:code|number|is)?\s*[:\-]?\s*\d{4,8}\b",
    re.IGNORECASE,
)
_PIN_PATTERN = re.compile(
    r"\b(?:pin|upi\s*pin|atm\s*pin)\s*(?:is|number|code)?\s*[:\-]?\s*\d{4,6}\b",
    re.IGNORECASE,
)
_CARD_PATTERN = re.compile(
    r"\b(?:\d[ -]?){13,19}\b",
)
_STANDALONE_OTP = re.compile(r"\b\d{4,8}\b")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sanitize_summary_text(text: str) -> str:
    """Strip OTP/PIN/card-like digit runs from free-text escalation fields."""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""

    cleaned = _OTP_PATTERN.sub("[redacted]", cleaned)
    cleaned = _PIN_PATTERN.sub("[redacted]", cleaned)
    cleaned = _CARD_PATTERN.sub("[redacted]", cleaned)

    # Standalone 6-digit runs often look like OTPs when no other digits nearby.
    if re.search(r"\botp\b", cleaned, re.IGNORECASE):
        cleaned = _STANDALONE_OTP.sub("[redacted]", cleaned)

    return re.sub(r"\s+", " ", cleaned).strip()


def _generate_reference_id() -> str:
    return f"ESC-{secrets.token_hex(2).upper()}"


@dataclass
class Escalation:
    reference_id: str
    created_at: str
    status: str
    reason: str
    urgency: str
    caller_name: str
    language: str
    preferred_followup: str
    what_happened: str
    already_checked: str
    caller_consented: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference_id": self.reference_id,
            "created_at": self.created_at,
            "status": self.status,
            "reason": self.reason,
            "urgency": self.urgency,
            "caller_name": self.caller_name,
            "language": self.language,
            "preferred_followup": self.preferred_followup,
            "what_happened": self.what_happened,
            "already_checked": self.already_checked,
            "caller_consented": self.caller_consented,
        }


class EscalationStore:
    """Thread-safe SQLite store with append-only JSONL mirror for the frontend."""

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
                CREATE TABLE IF NOT EXISTS escalations (
                    reference_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    reason TEXT NOT NULL,
                    urgency TEXT NOT NULL DEFAULT 'medium',
                    caller_name TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'en-IN',
                    preferred_followup TEXT NOT NULL DEFAULT '',
                    what_happened TEXT NOT NULL,
                    already_checked TEXT NOT NULL DEFAULT '',
                    caller_consented INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_escalations_status "
                "ON escalations(status, created_at DESC)"
            )
            conn.commit()

    def _row_to_escalation(self, row: sqlite3.Row) -> Escalation:
        return Escalation(
            reference_id=row["reference_id"],
            created_at=row["created_at"],
            status=row["status"],
            reason=row["reason"],
            urgency=row["urgency"],
            caller_name=row["caller_name"],
            language=row["language"],
            preferred_followup=row["preferred_followup"] or "",
            what_happened=row["what_happened"],
            already_checked=row["already_checked"] or "",
            caller_consented=bool(row["caller_consented"]),
        )

    def _append_jsonl(self, record: dict[str, Any]) -> None:
        if str(self.jsonl_path) == ":memory:":
            return
        line = json.dumps(record, ensure_ascii=False)
        with self.jsonl_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _unique_reference_id(self, conn: sqlite3.Connection) -> str:
        for _ in range(8):
            ref = _generate_reference_id()
            row = conn.execute(
                "SELECT 1 FROM escalations WHERE reference_id = ?",
                (ref,),
            ).fetchone()
            if row is None:
                return ref
        raise RuntimeError("Could not allocate a unique escalation reference id")

    def create(
        self,
        *,
        reason: str,
        what_happened: str,
        already_checked: str,
        urgency: str,
        preferred_followup: str,
        caller_name: str,
        language: str,
        caller_consented: bool,
    ) -> dict[str, Any]:
        if not caller_consented:
            return {
                "created": False,
                "reference_id": "",
                "message": (
                    "Escalation not created — caller consent is required before "
                    "sharing details with the shopkeeper."
                ),
            }

        reason_norm = (reason or "").strip()
        if reason_norm not in VALID_REASONS:
            return {
                "created": False,
                "reference_id": "",
                "message": (
                    "Escalation not created — reason must be "
                    "payment_refund_dispute or order_dispute."
                ),
            }

        if not (caller_name or "").strip():
            return {
                "created": False,
                "reference_id": "",
                "message": "Escalation not created — caller name is required.",
            }

        summary = sanitize_summary_text(what_happened)
        if not summary:
            return {
                "created": False,
                "reference_id": "",
                "message": (
                    "Escalation not created — need a short summary of what happened."
                ),
            }

        urgency_norm = (urgency or "medium").strip().lower() or "medium"
        if urgency_norm not in VALID_URGENCIES:
            urgency_norm = "medium"

        lang = (language or "en-IN").strip() or "en-IN"
        if lang not in VALID_LANGUAGES:
            lang = "en-IN"

        checked = sanitize_summary_text(already_checked)
        followup = sanitize_summary_text(preferred_followup)
        now = _utc_now_iso()

        with self._lock:
            conn = self._connect()
            ref = self._unique_reference_id(conn)
            conn.execute(
                """
                INSERT INTO escalations (
                    reference_id, created_at, status, reason, urgency,
                    caller_name, language, preferred_followup,
                    what_happened, already_checked, caller_consented
                ) VALUES (?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    ref,
                    now,
                    reason_norm,
                    urgency_norm,
                    caller_name.strip(),
                    lang,
                    followup,
                    summary,
                    checked,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM escalations WHERE reference_id = ?",
                (ref,),
            ).fetchone()

        assert row is not None
        escalation = self._row_to_escalation(row)
        self._append_jsonl(escalation.to_dict())

        return {
            "created": True,
            "reference_id": ref,
            "message": (
                f"Escalation {ref} logged for the shopkeeper. "
                "They will review and follow up — no instant callback is promised."
            ),
        }

    def list_open(self) -> list[Escalation]:
        with self._lock:
            conn = self._connect()
            rows = conn.execute(
                """
                SELECT * FROM escalations
                WHERE status = 'open'
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [self._row_to_escalation(row) for row in rows]
