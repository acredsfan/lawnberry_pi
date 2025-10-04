from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Tuple


class PersistenceLayer:
    """SQLite-backed persistence for critical messages (simplified).

    Uses a single table with (topic, timestamp_us, payload_json).
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS messages (topic TEXT, timestamp_us INTEGER, payload TEXT)"
        )
        self._conn.commit()

    def save(self, topic: str, timestamp_us: int, payload: Dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT INTO messages(topic, timestamp_us, payload) VALUES(?,?,?)",
            (topic, timestamp_us, json.dumps(payload)),
        )
        self._conn.commit()

    def load(self, topic: str) -> List[Tuple[int, Dict[str, Any]]]:
        cur = self._conn.execute(
            "SELECT timestamp_us, payload FROM messages WHERE topic=? ORDER BY timestamp_us ASC",
            (topic,),
        )
        rows = cur.fetchall()
        return [(ts, json.loads(payload)) for ts, payload in rows]
