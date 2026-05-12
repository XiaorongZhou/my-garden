from __future__ import annotations

from http import HTTPStatus
from sqlite3 import Connection

from .config import (
    AI_CHAT_DAILY_LIMIT,
    AI_CHECKIN_DAILY_LIMIT,
    AI_DAILY_LIMIT,
    AI_IDENTITY_DAILY_LIMIT,
)
from .data import ai_usage_count, increment_ai_usage, today_date_iso
from .errors import ApiError

AI_ACTION_LABELS = {
    "identity": "plant identification",
    "checkin": "diagnosis",
    "chat": "follow-up chat",
}

AI_ACTION_LIMITS = {
    "identity": AI_IDENTITY_DAILY_LIMIT,
    "checkin": AI_CHECKIN_DAILY_LIMIT,
    "chat": AI_CHAT_DAILY_LIMIT,
}


def consume_ai_quota(connection: Connection, *, user_id: str, action: str) -> None:
    usage_date = today_date_iso()
    action_limit = AI_ACTION_LIMITS.get(action, 0)
    action_count = ai_usage_count(
        connection,
        user_id=user_id,
        usage_date=usage_date,
        action=action,
    )
    if action_limit > 0 and action_count >= action_limit:
        label = AI_ACTION_LABELS.get(action, "AI")
        raise ApiError(
            HTTPStatus.TOO_MANY_REQUESTS,
            f"Daily {label} limit reached. Try again tomorrow.",
        )

    total_count = ai_usage_count(
        connection,
        user_id=user_id,
        usage_date=usage_date,
        action=None,
    )
    if AI_DAILY_LIMIT > 0 and total_count >= AI_DAILY_LIMIT:
        raise ApiError(
            HTTPStatus.TOO_MANY_REQUESTS,
            "Daily AI limit reached. Try again tomorrow.",
        )

    increment_ai_usage(
        connection,
        user_id=user_id,
        usage_date=usage_date,
        action=action,
    )
