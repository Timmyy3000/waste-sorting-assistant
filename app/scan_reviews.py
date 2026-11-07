"""Ownership-bound saved sorting choices and append-only correction history."""

import hashlib
import secrets
from datetime import datetime, timezone

from flask import session

from app.db import Database, ScanRepository
from app.disposal import CATEGORY, STREAMS
from app.routes.errors import UploadError


def owner_hash() -> str:
    if "scan_owner" not in session:
        session["scan_owner"] = secrets.token_urlsafe(32)
    return hashlib.sha256(session["scan_owner"].encode()).hexdigest()


def csrf_token() -> str:
    if "scan_csrf" not in session:
        session["scan_csrf"] = secrets.token_urlsafe(32)
    return session["scan_csrf"]


class ReviewRepository:
    def __init__(self, database: Database):
        self.database = database
        self.database.create_tables()

    def reconcile_pending(self) -> None:
        """Repair older suggestions that were incorrectly counted as choices."""
        self.database.execute(
            "UPDATE scans SET category = 'unknown' WHERE category != 'unknown' "
            "AND id IN (SELECT scan_id FROM scan_reviews WHERE status IN ('suggested', 'unresolved'))"
        )

    def create(self, scan_id: int, owner: str, stream: str, ai_result: dict, status: str | None = None) -> None:
        self.database.execute(
            "INSERT INTO scan_reviews (scan_id, owner_hash, stream, status, ai_category, ai_material, ai_confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (scan_id, owner, stream, status or ("unresolved" if stream == "unknown" else "suggested"),
             ai_result["category"], ai_result.get("ai_material", ai_result["material"]), ai_result["confidence"]),
        )

    def get_owned(self, scan_id: int, owner: str) -> dict | None:
        rows = self.database.query(
            "SELECT r.*, s.region, s.material, s.category, s.confidence, s.timestamp "
            "FROM scan_reviews r JOIN scans s ON s.id = r.scan_id "
            "WHERE r.scan_id = ? AND r.owner_hash = ?", (scan_id, owner),
        )
        return rows[0] if rows else None

    def history(self, owner: str, region=None, start=None, end=None) -> list[dict]:
        rows = self.database.query(
            "SELECT r.scan_id, r.stream, r.status, s.region, s.material, s.timestamp "
            "FROM scan_reviews r JOIN scans s ON s.id = r.scan_id "
            "WHERE r.owner_hash = ? ORDER BY s.timestamp DESC LIMIT 100", (owner,),
        )
        return [r for r in rows if (not region or r["region"] == region)
                and (not start or r["timestamp"][:10] >= start.isoformat())
                and (not end or r["timestamp"][:10] <= end.isoformat())]

    def stream_counts(self, scan_ids: list[int]) -> dict[str, int]:
        counts = dict.fromkeys(STREAMS, 0)
        for offset in range(0, len(scan_ids), 500):
            batch = scan_ids[offset:offset + 500]
            placeholders = ",".join("?" for _ in batch)
            rows = self.database.query(
                f"SELECT CASE WHEN status IN ('suggested', 'unresolved') THEN 'unknown' "
                f"ELSE stream END AS stream, COUNT(*) AS count FROM scan_reviews "
                f"WHERE scan_id IN ({placeholders}) GROUP BY CASE WHEN status IN "
                f"('suggested', 'unresolved') THEN 'unknown' ELSE stream END",
                tuple(batch),
            )
            for row in rows:
                counts[row["stream"]] += row["count"]
        return counts

    def correct(self, scan_id: int, owner: str, stream: str, material: str, expected_version: int) -> dict:
        if stream not in STREAMS or stream == "unknown":
            raise UploadError("Choose a specific disposal route after identifying the item.")
        material = material.strip() if isinstance(material, str) else ""
        if not 1 <= len(material) <= 120:
            raise UploadError("Describe the identified item in 1–120 characters.")
        current = self.get_owned(scan_id, owner)
        if current is None:
            raise UploadError("This scan is not available in your browser session.")
        if current["version"] != expected_version:
            raise UploadError("This result changed. Reload it before correcting again.")
        status = "confirmed" if stream == current["stream"] and material == current["material"] and current["status"] != "corrected" else "corrected"
        now = datetime.now(timezone.utc).isoformat()
        # Update both tables and audit entry in one transaction. Conditional
        # version update rejects stale submissions, including concurrent edits.
        cursor = self.database.connection.cursor()
        try:
            cursor.execute(self.database._convert_sql(
                "UPDATE scan_reviews SET stream=?, status=?, version=version+1 WHERE scan_id=? AND owner_hash=? AND version=?"),
                (stream, status, scan_id, owner, expected_version))
            if cursor.rowcount != 1:
                raise UploadError("This result changed. Reload it before correcting again.")
            cursor.execute(self.database._convert_sql(
                "UPDATE scans SET category=?, material=?, corrected=? WHERE id=?"),
                (CATEGORY[stream], material, int(status == "corrected"), scan_id))
            cursor.execute(self.database._convert_sql(
                "INSERT INTO scan_corrections (scan_id, changed_at, old_stream, new_stream, old_material, new_material) "
                "VALUES (?, ?, ?, ?, ?, ?)"),
                (scan_id, now, current["stream"], stream, current["material"], material))
            self.database.connection.commit()
        except Exception:
            self.database.connection.rollback()
            raise
        return self.get_owned(scan_id, owner)
