# SQLite cache for LLM market extractions (scans read only; populate on demand).
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from config import LLM_CACHE_PATH
from llm_market_payload import cache_key_for_market, content_hash_for_market

_lock = threading.Lock()
_conn = None


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _ensure_parent(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _get_connection():
    global _conn
    if _conn is None:
        _ensure_parent(LLM_CACHE_PATH)
        _conn = sqlite3.connect(LLM_CACHE_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _init_schema(_conn)
    return _conn


def _init_schema(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_extractions (
            cache_key TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            market_id TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            extraction_json TEXT NOT NULL,
            valid INTEGER NOT NULL DEFAULT 1,
            validation_errors TEXT,
            model TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_market_extractions_platform ON market_extractions(platform)"
    )
    conn.commit()


def get_cached_record(market):
    """Return cached record dict or None."""
    key = cache_key_for_market(market)
    with _lock:
        conn = _get_connection()
        row = conn.execute(
            "SELECT * FROM market_extractions WHERE cache_key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return None

    current_hash = content_hash_for_market(market)
    if row["content_hash"] != current_hash:
        return None

    try:
        extraction = json.loads(row["extraction_json"])
    except json.JSONDecodeError:
        return None

    return {
        "cache_key": row["cache_key"],
        "platform": row["platform"],
        "market_id": row["market_id"],
        "content_hash": row["content_hash"],
        "extraction": extraction,
        "valid": bool(row["valid"]),
        "validation_errors": json.loads(row["validation_errors"] or "[]"),
        "model": row["model"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def save_cached_record(market, extraction, valid, validation_errors=None, model=None):
    """Upsert extraction into cache."""
    key = cache_key_for_market(market)
    platform = market.get("platform") or "Unknown"
    market_id = key.split(":", 1)[-1]
    content_hash = content_hash_for_market(market)
    now = _utc_now()
    errors_json = json.dumps(list(validation_errors or []))
    extraction_json = json.dumps(extraction, ensure_ascii=True)

    with _lock:
        conn = _get_connection()
        existing = conn.execute(
            "SELECT created_at FROM market_extractions WHERE cache_key = ?",
            (key,),
        ).fetchone()
        created_at = existing["created_at"] if existing else now

        conn.execute(
            """
            INSERT INTO market_extractions (
                cache_key, platform, market_id, content_hash, extraction_json,
                valid, validation_errors, model, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                content_hash = excluded.content_hash,
                extraction_json = excluded.extraction_json,
                valid = excluded.valid,
                validation_errors = excluded.validation_errors,
                model = excluded.model,
                updated_at = excluded.updated_at
            """,
            (
                key,
                platform,
                market_id,
                content_hash,
                extraction_json,
                1 if valid else 0,
                errors_json,
                model,
                created_at,
                now,
            ),
        )
        conn.commit()


def cache_stats():
    """Return aggregate cache statistics."""
    with _lock:
        conn = _get_connection()
        try:
            total = conn.execute("SELECT COUNT(*) AS c FROM market_extractions").fetchone()["c"]
            valid = conn.execute(
                "SELECT COUNT(*) AS c FROM market_extractions WHERE valid = 1"
            ).fetchone()["c"]
            by_platform = conn.execute(
                """
                SELECT platform, COUNT(*) AS c
                FROM market_extractions
                GROUP BY platform
                ORDER BY c DESC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return {"total": 0, "valid": 0, "by_platform": {}}

    return {
        "total": total,
        "valid": valid,
        "invalid": total - valid,
        "by_platform": {row["platform"]: row["c"] for row in by_platform},
        "path": str(LLM_CACHE_PATH),
    }


def close_cache():
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
