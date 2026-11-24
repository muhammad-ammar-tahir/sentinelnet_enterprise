"""backend/services/audit_service.py — Structured Audit Logging.

Persists destructive actions to both PostgreSQL `audit_logs` table AND
an append-only `logs/audit.jsonl` file in structured JSON format.
"""

import os
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.models import AuditLog

logger = logging.getLogger("sentinelnet.audit")
AUDIT_LOG_FILE = "logs/audit.jsonl"


async def record_audit_log(
    db: Optional[AsyncSession],
    action: str,
    actor: str,
    details: Dict[str, Any]
) -> Dict[str, Any]:
    """Record an audit log entry in the database AND in logs/audit.jsonl."""
    log_id = f"audit-{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    entry = {
        "id": log_id,
        "timestamp": now_iso,
        "action": action,
        "actor": actor,
        "details": details
    }

    # 1. Append to append-only JSONL file
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.error("Failed to write to audit file %s: %s", AUDIT_LOG_FILE, exc)

    # 2. Persist to audit_logs table if DB session provided
    if db is not None:
        try:
            db_record = AuditLog(
                id=log_id,
                action=action,
                actor=actor,
                details=details,
                created_at=datetime.now(timezone.utc)
            )
            db.add(db_record)
            await db.commit()
        except Exception as exc:
            logger.error("Failed to persist AuditLog to database: %s", exc)

    logger.info("AUDIT LOG [%s] by '%s': %s", action, actor, details)
    return entry
