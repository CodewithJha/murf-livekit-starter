"""SQLite persistence for Dukaan Dost caller memory (Voice for Bharat Day 4)."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "dukaan_dost.db"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_user_id(name: str) -> str:
    """Stable id from a spoken name (case-insensitive, alphanumeric slug)."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "unknown"


@dataclass
class CallerProfile:
    user_id: str
    name: str
    language_preference: str
    facts: dict[str, Any]
    last_interaction: str
    livekit_identity: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "language_preference": self.language_preference,
            "facts": self.facts,
            "last_interaction": self.last_interaction,
            "livekit_identity": self.livekit_identity,
        }


class MemoryStore:
    """Thread-safe SQLite store for caller profiles."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        # Keep a shared connection for :memory: so tables survive across calls.
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
                CREATE TABLE IF NOT EXISTS callers (
                    user_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    language_preference TEXT NOT NULL DEFAULT 'en-IN',
                    facts_json TEXT NOT NULL DEFAULT '{}',
                    last_interaction TEXT NOT NULL,
                    livekit_identity TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_callers_name "
                "ON callers(name COLLATE NOCASE)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_callers_identity "
                "ON callers(livekit_identity)"
            )
            conn.commit()

    def _row_to_profile(self, row: sqlite3.Row) -> CallerProfile:
        try:
            facts = json.loads(row["facts_json"] or "{}")
        except json.JSONDecodeError:
            facts = {}
        if not isinstance(facts, dict):
            facts = {"value": facts}
        return CallerProfile(
            user_id=row["user_id"],
            name=row["name"],
            language_preference=row["language_preference"] or "en-IN",
            facts=facts,
            last_interaction=row["last_interaction"],
            livekit_identity=row["livekit_identity"],
        )

    def lookup_by_user_id(self, user_id: str) -> CallerProfile | None:
        if not user_id:
            return None
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM callers WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def lookup_by_name(self, name: str) -> CallerProfile | None:
        if not (name or "").strip():
            return None
        user_id = normalize_user_id(name)
        by_id = self.lookup_by_user_id(user_id)
        if by_id is not None:
            return by_id
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM callers WHERE name = ? COLLATE NOCASE",
                (name.strip(),),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def lookup_by_identity(self, livekit_identity: str) -> CallerProfile | None:
        if not (livekit_identity or "").strip():
            return None
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM callers WHERE livekit_identity = ?",
                (livekit_identity.strip(),),
            ).fetchone()
        return self._row_to_profile(row) if row else None

    def save(
        self,
        *,
        name: str,
        language_preference: str,
        facts: dict[str, Any],
        livekit_identity: str | None = None,
        user_id: str | None = None,
    ) -> CallerProfile:
        if not (name or "").strip():
            raise ValueError("name is required")
        uid = user_id or normalize_user_id(name)
        lang = (language_preference or "en-IN").strip() or "en-IN"
        now = _utc_now_iso()
        facts_json = json.dumps(facts or {}, ensure_ascii=False)
        identity = (livekit_identity or "").strip() or None

        with self._lock:
            conn = self._connect()
            existing = conn.execute(
                "SELECT facts_json, livekit_identity FROM callers WHERE user_id = ?",
                (uid,),
            ).fetchone()
            if existing is not None:
                try:
                    prev_facts = json.loads(existing["facts_json"] or "{}")
                except json.JSONDecodeError:
                    prev_facts = {}
                if isinstance(prev_facts, dict):
                    merged = {**prev_facts, **(facts or {})}
                else:
                    merged = dict(facts or {})
                facts_json = json.dumps(merged, ensure_ascii=False)
                if identity is None:
                    identity = existing["livekit_identity"]

            conn.execute(
                """
                INSERT INTO callers (
                    user_id, name, language_preference, facts_json,
                    last_interaction, livekit_identity
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    name = excluded.name,
                    language_preference = excluded.language_preference,
                    facts_json = excluded.facts_json,
                    last_interaction = excluded.last_interaction,
                    livekit_identity = COALESCE(
                        excluded.livekit_identity, callers.livekit_identity
                    )
                """,
                (uid, name.strip(), lang, facts_json, now, identity),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM callers WHERE user_id = ?",
                (uid,),
            ).fetchone()

        assert row is not None
        return self._row_to_profile(row)

    def delete(self, user_id: str) -> bool:
        with self._lock:
            conn = self._connect()
            cur = conn.execute("DELETE FROM callers WHERE user_id = ?", (user_id,))
            conn.commit()
            return cur.rowcount > 0
