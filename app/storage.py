from __future__ import annotations

import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MeasurementStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._write_lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS measurements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    axis TEXT NOT NULL,
                    value REAL NOT NULL,
                    unit TEXT NOT NULL,
                    raw TEXT,
                    received_at TEXT NOT NULL,
                    stored_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS measurements_stored_at_idx ON measurements(stored_at DESC)"
            )

    def add(
        self,
        axis: str,
        value: float,
        unit: str = "mm",
        raw: str | None = None,
        received_at: str | None = None,
    ) -> dict[str, Any]:
        rows = self.add_snapshot(
            [{"axis": axis, "value": value, "unit": unit, "raw": raw, "received_at": received_at}]
        )
        return rows[0]

    def add_snapshot(self, measurements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not measurements:
            raise ValueError("At least one measurement is required")

        stored = utc_now()
        normalized: list[dict[str, Any]] = []
        for measurement in measurements:
            axis = str(measurement.get("axis", "")).strip().upper()
            unit = str(measurement.get("unit", "mm")).strip().lower()
            if not axis:
                raise ValueError("Axis is required")
            if not unit:
                raise ValueError("Unit is required")
            normalized.append(
                {
                    "axis": axis,
                    "value": float(measurement["value"]),
                    "unit": unit,
                    "raw": measurement.get("raw"),
                    "received_at": str(measurement.get("received_at") or stored),
                }
            )

        saved: list[dict[str, Any]] = []
        with self._write_lock, closing(self._connect()) as connection, connection:
            for measurement in normalized:
                cursor = connection.execute(
                    """
                    INSERT INTO measurements(axis, value, unit, raw, received_at, stored_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        measurement["axis"],
                        measurement["value"],
                        measurement["unit"],
                        measurement["raw"],
                        measurement["received_at"],
                        stored,
                    ),
                )
                saved.append({"id": cursor.lastrowid, **measurement, "stored_at": stored})
        return saved

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 1000))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT id, axis, value, unit, raw, received_at, stored_at
                FROM measurements
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            count = connection.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
            latest = connection.execute(
                """
                SELECT id, axis, value, unit, raw, received_at, stored_at
                FROM measurements
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return {"count": count, "latest": dict(latest) if latest else None}
