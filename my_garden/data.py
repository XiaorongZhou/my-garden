from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime

from .auth import (
    hash_password,
    new_session_token,
    session_expires_at,
    session_token_digest,
    verify_password,
)
from .config import DB_PATH, DEMO_CAT_PALM_ID, DEMO_MAIDENHAIR_ID, SESSION_TTL_DAYS
from .errors import ApiError
from .http_utils import thumbnail_url_for
from .plant_ai import default_tip_for_identity, heuristic_chinese_name

REFERENCE_NOTE_TEXTS = {
    "Gets crispy quickly when the air feels dry.",
    "Likes even moisture and brighter mornings.",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def today_date_iso() -> str:
    return datetime.now().date().isoformat()


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_email(value: str) -> str:
    return str(value or "").strip().lower()


def init_db() -> None:
    with get_conn() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                normalized_email TEXT,
                password_hash TEXT NOT NULL DEFAULT '',
                is_claimable INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_normalized_email ON users(normalized_email)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_digest TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                user_id TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                action TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, usage_date, action),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS plants (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                name TEXT NOT NULL,
                species TEXT NOT NULL,
                chinese_name TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL,
                notes TEXT NOT NULL,
                note_origin TEXT NOT NULL DEFAULT 'empty',
                tip_title TEXT NOT NULL DEFAULT '',
                tip_body TEXT NOT NULL DEFAULT '',
                tip_source TEXT NOT NULL DEFAULT 'empty',
                cover_photo_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS checkins (
                id TEXT PRIMARY KEY,
                plant_id TEXT NOT NULL,
                note TEXT NOT NULL,
                photo_url TEXT,
                health_status TEXT NOT NULL,
                diagnosis_title TEXT NOT NULL,
                diagnosis_summary TEXT NOT NULL,
                care_steps_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (plant_id) REFERENCES plants(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_threads (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                plant_id TEXT NOT NULL,
                rolling_summary TEXT NOT NULL DEFAULT '',
                open_questions_json TEXT NOT NULL DEFAULT '[]',
                last_advice_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (plant_id) REFERENCES plants(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                plant_id TEXT NOT NULL,
                checkin_id TEXT,
                role TEXT NOT NULL,
                body TEXT NOT NULL,
                suggested_actions_json TEXT NOT NULL DEFAULT '[]',
                watch_signals_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES chat_threads(id),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (plant_id) REFERENCES plants(id),
                FOREIGN KEY (checkin_id) REFERENCES checkins(id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS waterings (
                id TEXT PRIMARY KEY,
                plant_id TEXT NOT NULL,
                watered_on TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (plant_id) REFERENCES plants(id)
            )
            """
        )
        columns = {
            str(row["name"]): row
            for row in connection.execute("PRAGMA table_info(plants)").fetchall()
        }
        user_columns = {
            str(row["name"]): row
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        thread_columns = {
            str(row["name"]): row
            for row in connection.execute("PRAGMA table_info(chat_threads)").fetchall()
        }
        message_columns = {
            str(row["name"]): row
            for row in connection.execute("PRAGMA table_info(chat_messages)").fetchall()
        }
        if "password_hash" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''"
            )
        if "note_origin" not in columns:
            connection.execute(
                "ALTER TABLE plants ADD COLUMN note_origin TEXT NOT NULL DEFAULT 'empty'"
            )
        if "user_id" not in columns:
            connection.execute("ALTER TABLE plants ADD COLUMN user_id TEXT")
        if "chinese_name" not in columns:
            connection.execute(
                "ALTER TABLE plants ADD COLUMN chinese_name TEXT NOT NULL DEFAULT ''"
            )
        if "tip_title" not in columns:
            connection.execute(
                "ALTER TABLE plants ADD COLUMN tip_title TEXT NOT NULL DEFAULT ''"
            )
        if "tip_body" not in columns:
            connection.execute(
                "ALTER TABLE plants ADD COLUMN tip_body TEXT NOT NULL DEFAULT ''"
            )
        if "tip_source" not in columns:
            connection.execute(
                "ALTER TABLE plants ADD COLUMN tip_source TEXT NOT NULL DEFAULT 'empty'"
            )
        if "rolling_summary" not in thread_columns:
            connection.execute(
                "ALTER TABLE chat_threads ADD COLUMN rolling_summary TEXT NOT NULL DEFAULT ''"
            )
        if "open_questions_json" not in thread_columns:
            connection.execute(
                "ALTER TABLE chat_threads ADD COLUMN open_questions_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "last_advice_json" not in thread_columns:
            connection.execute(
                "ALTER TABLE chat_threads ADD COLUMN last_advice_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "suggested_actions_json" not in message_columns:
            connection.execute(
                "ALTER TABLE chat_messages ADD COLUMN suggested_actions_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "watch_signals_json" not in message_columns:
            connection.execute(
                "ALTER TABLE chat_messages ADD COLUMN watch_signals_json TEXT NOT NULL DEFAULT '[]'"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_plants_user_id ON plants(user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_user_sessions_token_digest ON user_sessions(token_digest)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_usage_user_day ON ai_usage(user_id, usage_date)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_checkins_plant_id ON checkins(plant_id)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_chat_threads_user_plant ON chat_threads(user_id, plant_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_threads_user_id ON chat_threads(user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_thread_id ON chat_messages(thread_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_plant_id ON chat_messages(plant_id)"
        )
        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_waterings_plant_day ON waterings(plant_id, watered_on)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_waterings_plant_id ON waterings(plant_id)"
        )
        connection.commit()
        migrate_users_and_ownership(connection)
        migrate_note_origins(connection)
        migrate_tip_fields(connection)


def json_dumps(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"))


def json_loads(raw: str | None, fallback: object) -> object:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def create_user(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    name: str,
    email: str,
    normalized_email: str | None,
    is_claimable: bool,
    created_at: str,
    password_hash: str = "",
) -> None:
    connection.execute(
        """
        INSERT INTO users (
            id, name, email, normalized_email, password_hash, is_claimable, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            name,
            email,
            normalized_email,
            password_hash,
            1 if is_claimable else 0,
            created_at,
            created_at,
        ),
    )


def create_plant(
    connection: sqlite3.Connection,
    *,
    plant_id: str,
    user_id: str,
    name: str,
    species: str,
    chinese_name: str,
    location: str,
    notes: str,
    note_origin: str,
    tip_title: str,
    tip_body: str,
    tip_source: str,
    cover_photo_url: str | None,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO plants (
            id, user_id, name, species, chinese_name, location, notes, note_origin, tip_title,
            tip_body, tip_source, cover_photo_url, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            plant_id,
            user_id,
            name,
            species,
            chinese_name,
            location,
            notes,
            note_origin,
            tip_title,
            tip_body,
            tip_source,
            cover_photo_url,
            created_at,
            created_at,
        ),
    )


def create_checkin(
    connection: sqlite3.Connection,
    *,
    checkin_id: str,
    plant_id: str,
    note: str,
    photo_url: str | None,
    health_status: str,
    diagnosis_title: str,
    diagnosis_summary: str,
    care_steps: list[str],
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO checkins (
            id, plant_id, note, photo_url, health_status, diagnosis_title,
            diagnosis_summary, care_steps_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            checkin_id,
            plant_id,
            note,
            photo_url,
            health_status,
            diagnosis_title,
            diagnosis_summary,
            json_dumps(care_steps),
            created_at,
        ),
    )
    connection.execute("UPDATE plants SET updated_at = ? WHERE id = ?", (created_at, plant_id))


def create_chat_thread(
    connection: sqlite3.Connection,
    *,
    thread_id: str,
    user_id: str,
    plant_id: str,
    created_at: str,
    rolling_summary: str = "",
    open_questions: list[str] | None = None,
    last_advice: list[str] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO chat_threads (
            id, user_id, plant_id, rolling_summary, open_questions_json, last_advice_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            thread_id,
            user_id,
            plant_id,
            rolling_summary.strip(),
            json_dumps(open_questions or []),
            json_dumps(last_advice or []),
            created_at,
            created_at,
        ),
    )


def create_chat_message(
    connection: sqlite3.Connection,
    *,
    message_id: str,
    thread_id: str,
    user_id: str,
    plant_id: str,
    checkin_id: str | None,
    role: str,
    body: str,
    suggested_actions: list[str] | None,
    watch_signals: list[str] | None,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO chat_messages (
            id, thread_id, user_id, plant_id, checkin_id, role, body,
            suggested_actions_json, watch_signals_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            message_id,
            thread_id,
            user_id,
            plant_id,
            checkin_id,
            role,
            body.strip(),
            json_dumps(suggested_actions or []),
            json_dumps(watch_signals or []),
            created_at,
        ),
    )
    connection.execute(
        "UPDATE chat_threads SET updated_at = ? WHERE id = ?",
        (created_at, thread_id),
    )


def create_watering_event(
    connection: sqlite3.Connection,
    *,
    watering_id: str,
    plant_id: str,
    watered_on: str,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO waterings (
            id, plant_id, watered_on, created_at
        )
        VALUES (?, ?, ?, ?)
        """,
        (
            watering_id,
            plant_id,
            watered_on,
            created_at,
        ),
    )
    connection.execute("UPDATE plants SET updated_at = ? WHERE id = ?", (created_at, plant_id))


def create_user_session(connection: sqlite3.Connection, *, user_id: str) -> str:
    created_at = now_iso()
    token = new_session_token()
    connection.execute(
        """
        INSERT INTO user_sessions (
            id, user_id, token_digest, created_at, expires_at, last_seen_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            user_id,
            session_token_digest(token),
            created_at,
            session_expires_at(days=SESSION_TTL_DAYS),
            created_at,
        ),
    )
    return token


def fetch_user_by_session_token(
    connection: sqlite3.Connection,
    token: str,
) -> sqlite3.Row | None:
    cleaned = str(token or "").strip()
    if not cleaned:
        return None
    row = connection.execute(
        """
        SELECT u.*
        FROM user_sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_digest = ?
          AND datetime(s.expires_at) > datetime('now')
        """,
        (session_token_digest(cleaned),),
    ).fetchone()
    if row is not None:
        connection.execute(
            "UPDATE user_sessions SET last_seen_at = ? WHERE token_digest = ?",
            (now_iso(), session_token_digest(cleaned)),
        )
    return row


def ai_usage_count(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    usage_date: str,
    action: str | None,
) -> int:
    if action is None:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(count), 0) AS total
            FROM ai_usage
            WHERE user_id = ? AND usage_date = ?
            """,
            (user_id, usage_date),
        ).fetchone()
        return int(row["total"] or 0)
    row = connection.execute(
        """
        SELECT count
        FROM ai_usage
        WHERE user_id = ? AND usage_date = ? AND action = ?
        """,
        (user_id, usage_date, action),
    ).fetchone()
    return int(row["count"] if row is not None else 0)


def increment_ai_usage(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    usage_date: str,
    action: str,
) -> None:
    updated_at = now_iso()
    connection.execute(
        """
        INSERT INTO ai_usage (user_id, usage_date, action, count, updated_at)
        VALUES (?, ?, ?, 1, ?)
        ON CONFLICT(user_id, usage_date, action)
        DO UPDATE SET count = count + 1, updated_at = excluded.updated_at
        """,
        (user_id, usage_date, action, updated_at),
    )


def ensure_claimable_user(connection: sqlite3.Connection) -> str:
    row = connection.execute(
        "SELECT * FROM users WHERE is_claimable = 1 ORDER BY datetime(created_at) ASC LIMIT 1"
    ).fetchone()
    if row is not None:
        return str(row["id"])

    created_at = now_iso()
    user_id = str(uuid.uuid4())
    create_user(
        connection,
        user_id=user_id,
        name="Shared Garden",
        email="",
        normalized_email=None,
        password_hash="",
        is_claimable=True,
        created_at=created_at,
    )
    return user_id


def migrate_users_and_ownership(connection: sqlite3.Connection) -> None:
    missing_user_rows = connection.execute(
        "SELECT id FROM plants WHERE COALESCE(TRIM(user_id), '') = ''"
    ).fetchall()
    if not missing_user_rows:
        return

    claimable_user_id = ensure_claimable_user(connection)
    connection.execute(
        "UPDATE plants SET user_id = ? WHERE COALESCE(TRIM(user_id), '') = ''",
        (claimable_user_id,),
    )
    connection.commit()


def serialize_user(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "is_claimable": bool(row["is_claimable"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def fetch_user_by_id(connection: sqlite3.Connection, user_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise ApiError(401, "Choose your garden profile first.")
    return row


def find_user_by_email(connection: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    normalized = normalize_email(email)
    if not normalized:
        return None
    return connection.execute(
        "SELECT * FROM users WHERE normalized_email = ?",
        (normalized,),
    ).fetchone()


def has_claimable_user(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT 1 FROM users WHERE is_claimable = 1 LIMIT 1"
    ).fetchone()
    return row is not None


def create_or_claim_user(
    connection: sqlite3.Connection,
    *,
    name: str,
    email: str,
    password: str,
) -> tuple[sqlite3.Row, bool, bool]:
    cleaned_name = str(name or "").strip()
    cleaned_email = str(email or "").strip()
    cleaned_password = str(password or "")
    normalized = normalize_email(cleaned_email)
    if not normalized or "@" not in normalized:
        raise ApiError(400, "Add a valid email so your garden follows you across devices.")
    if len(cleaned_password) < 8:
        raise ApiError(400, "Use a password with at least 8 characters.")

    existing = find_user_by_email(connection, cleaned_email)
    updated_at = now_iso()
    if existing is not None:
        stored_hash = str(existing["password_hash"] or "")
        if stored_hash:
            if not verify_password(cleaned_password, stored_hash):
                raise ApiError(401, "That password does not match this garden.")
        else:
            connection.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
                (hash_password(cleaned_password), updated_at, existing["id"]),
            )
            existing = fetch_user_by_id(connection, str(existing["id"]))
        if cleaned_name and cleaned_name != str(existing["name"] or "").strip():
            connection.execute(
                "UPDATE users SET name = ?, email = ?, updated_at = ? WHERE id = ?",
                (cleaned_name, cleaned_email, updated_at, existing["id"]),
            )
            existing = fetch_user_by_id(connection, str(existing["id"]))
        return existing, False, not stored_hash

    if not cleaned_name:
        raise ApiError(400, "Add your name to create a new garden.")

    claimable = connection.execute(
        "SELECT * FROM users WHERE is_claimable = 1 ORDER BY datetime(created_at) ASC LIMIT 1"
    ).fetchone()
    if claimable is not None:
        connection.execute(
            """
            UPDATE users
            SET name = ?, email = ?, normalized_email = ?, is_claimable = 0, updated_at = ?
            , password_hash = ?
            WHERE id = ?
            """,
            (
                cleaned_name,
                cleaned_email,
                normalized,
                updated_at,
                hash_password(cleaned_password),
                claimable["id"],
            ),
        )
        return fetch_user_by_id(connection, str(claimable["id"])), True, True

    user_id = str(uuid.uuid4())
    create_user(
        connection,
        user_id=user_id,
        name=cleaned_name,
        email=cleaned_email,
        normalized_email=normalized,
        password_hash=hash_password(cleaned_password),
        is_claimable=False,
        created_at=updated_at,
    )
    return fetch_user_by_id(connection, user_id), False, True


def ensure_demo_seeded() -> None:
    with get_conn() as connection:
        plant_count = connection.execute("SELECT COUNT(*) FROM plants").fetchone()[0]
        if plant_count:
            return

        now = now_iso()
        claimable_user_id = ensure_claimable_user(connection)
        create_plant(
            connection,
            plant_id=DEMO_MAIDENHAIR_ID,
            user_id=claimable_user_id,
            name="Maidenhair Fern",
            species="Adiantum raddianum",
            chinese_name="铁线蕨",
            location="Bathroom shelf",
            notes="",
            note_origin="empty",
            tip_title="Care tip",
            tip_body="Gets crispy quickly when the air feels dry.",
            tip_source="reference",
            cover_photo_url="/static/demo/maidenhair-2.jpeg",
            created_at=now,
        )
        create_plant(
            connection,
            plant_id=DEMO_CAT_PALM_ID,
            user_id=claimable_user_id,
            name="Cat Palm",
            species="Chamaedorea cataractarum",
            chinese_name="猫棕",
            location="Living room corner",
            notes="",
            note_origin="empty",
            tip_title="Care tip",
            tip_body="Likes even moisture and brighter mornings.",
            tip_source="reference",
            cover_photo_url="/static/demo/cat-palm-2.jpeg",
            created_at=now,
        )

        create_checkin(
            connection,
            checkin_id="fern-checkin-1",
            plant_id=DEMO_MAIDENHAIR_ID,
            note="Edges looked crispy even though the soil still felt a little damp.",
            photo_url="/static/demo/maidenhair-1.jpeg",
            health_status="watch",
            diagnosis_title="Dry air is the main stress signal",
            diagnosis_summary="This fern looks more humidity-sensitive than thirsty right now, so hold off on extra watering.",
            care_steps=[
                "Keep it away from dry air for the next day.",
                "Check the top inch of soil tomorrow before watering.",
                "Compare the fronds again after a steamier morning.",
            ],
            created_at="2026-04-22T09:30:00",
        )
        create_checkin(
            connection,
            checkin_id="fern-checkin-2",
            plant_id=DEMO_MAIDENHAIR_ID,
            note="New fronds feel softer this week, but a few edges still curl at night.",
            photo_url="/static/demo/maidenhair-2.jpeg",
            health_status="thriving",
            diagnosis_title="Recovering well with softer growth",
            diagnosis_summary="The newest fronds suggest the plant is bouncing back. Stay consistent and do not overcorrect.",
            care_steps=[
                "Keep the current watering rhythm steady.",
                "Trim only fully dry fronds.",
                "Do another photo check-in in two days.",
            ],
            created_at="2026-04-26T08:10:00",
        )
        create_checkin(
            connection,
            checkin_id="cat-checkin-1",
            plant_id=DEMO_CAT_PALM_ID,
            note="The fronds looked flatter after a dry week in the living room.",
            photo_url="/static/demo/cat-palm-1.jpeg",
            health_status="watch",
            diagnosis_title="Early dryness is showing up",
            diagnosis_summary="The plant looks a little tired, but not severely stressed yet. Watch soil moisture closely.",
            care_steps=[
                "Check whether the topsoil feels dry tonight.",
                "Rotate the pot slightly toward the window.",
                "Re-check frond posture tomorrow morning.",
            ],
            created_at="2026-04-23T18:20:00",
        )
        create_checkin(
            connection,
            checkin_id="cat-checkin-2",
            plant_id=DEMO_CAT_PALM_ID,
            note="Lower fronds droop by evening and the topsoil finally feels dry.",
            photo_url="/static/demo/cat-palm-2.jpeg",
            health_status="needs_care",
            diagnosis_title="This one likely needs water today",
            diagnosis_summary="Dry topsoil plus evening droop points toward simple thirst more than anything else.",
            care_steps=[
                "Give it a full watering today.",
                "Let excess water drain before returning it to the pot tray.",
                "Take another photo tomorrow to confirm the fronds perk up.",
            ],
            created_at="2026-04-26T19:05:00",
        )

        connection.commit()


def normalize_legacy_checkins() -> None:
    legacy_title = "Photo saved. Add a note for a sharper read next time"
    legacy_summary = "The demo can store the photo and give a better diagnosis when you describe what changed since the last check-in."
    updated_title = "Photo saved. Add one quick observation next time"
    updated_summary = "I saved the photo, but I still need one quick observation next time to make the diagnosis specific."

    with get_conn() as connection:
        connection.execute(
            """
            UPDATE checkins
            SET diagnosis_title = ?,
                diagnosis_summary = ?,
                care_steps_json = ?
            WHERE diagnosis_title = ?
              AND diagnosis_summary = ?
              AND TRIM(note) = ''
            """,
            (
                updated_title,
                updated_summary,
                json_dumps([]),
                legacy_title,
                legacy_summary,
            ),
        )
        connection.execute(
            """
            UPDATE checkins
            SET diagnosis_summary = ?,
                care_steps_json = ?
            WHERE diagnosis_title = ?
              AND TRIM(note) = ''
            """,
            (
                updated_summary,
                json_dumps([]),
                updated_title,
            ),
        )
        connection.commit()


def infer_note_origin(notes: str) -> str:
    normalized = str(notes or "").strip()
    if not normalized:
        return "empty"
    if normalized in REFERENCE_NOTE_TEXTS:
        return "reference"
    return "user"


def migrate_note_origins(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        UPDATE plants
        SET note_origin = CASE
            WHEN TRIM(notes) = '' THEN 'empty'
            WHEN TRIM(notes) IN (?, ?) THEN 'reference'
            ELSE 'user'
        END
        WHERE note_origin NOT IN ('empty', 'user', 'reference')
           OR note_origin IS NULL
           OR (
                note_origin = 'empty'
                AND TRIM(notes) != ''
           )
           OR (
                note_origin = 'user'
                AND TRIM(notes) IN (?, ?)
           )
        """,
        (
            "Gets crispy quickly when the air feels dry.",
            "Likes even moisture and brighter mornings.",
            "Gets crispy quickly when the air feels dry.",
            "Likes even moisture and brighter mornings.",
        ),
    )
    connection.commit()


def migrate_tip_fields(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT * FROM plants").fetchall()
    for row in rows:
        updates: list[str] = []
        params: list[object] = []

        chinese_name = str(row["chinese_name"] or "").strip()
        if not chinese_name:
            guessed_chinese_name = heuristic_chinese_name(
                name=str(row["name"] or ""),
                species=str(row["species"] or ""),
            )
            if guessed_chinese_name:
                updates.append("chinese_name = ?")
                params.append(guessed_chinese_name)

        tip_title = str(row["tip_title"] or "").strip()
        tip_body = str(row["tip_body"] or "").strip()
        tip_source = str(row["tip_source"] or "").strip().lower()
        legacy_notes = str(row["notes"] or "").strip()
        note_origin = str(row["note_origin"] or "").strip().lower()

        next_tip = None
        if not tip_body and legacy_notes:
            next_tip = {
                "title": "Care tip" if note_origin == "reference" else "Saved context",
                "body": legacy_notes,
                "source": "reference" if note_origin == "reference" else "legacy",
            }
        elif not tip_body:
            next_tip = default_tip_for_identity(
                name=str(row["name"] or ""),
                species=str(row["species"] or ""),
            )

        if next_tip:
            updates.extend([
                "tip_title = ?",
                "tip_body = ?",
                "tip_source = ?",
            ])
            params.extend([
                str(next_tip["title"]).strip() or "Care tip",
                str(next_tip["body"]).strip(),
                str(next_tip["source"]).strip() or "reference",
            ])
        elif tip_body and not tip_title:
            updates.append("tip_title = ?")
            params.append("Care tip")
        elif tip_body and tip_source not in {"reference", "heuristic", "model", "legacy"}:
            updates.append("tip_source = ?")
            params.append("reference")

        if legacy_notes and next_tip and str(next_tip["body"]).strip() == legacy_notes:
            updates.extend([
                "notes = ?",
                "note_origin = ?",
            ])
            params.extend(["", "empty"])

        if updates:
            params.append(str(row["id"]))
            connection.execute(
                f"UPDATE plants SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    connection.commit()


def is_uuid_string(value: str) -> bool:
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (ValueError, AttributeError):
        return False


def migrate_plant_ids_to_uuid() -> None:
    with get_conn() as connection:
        rows = connection.execute("SELECT id FROM plants").fetchall()
        existing_ids = {str(row["id"]) for row in rows}
        migrations: dict[str, str] = {}

        for row in rows:
            old_id = str(row["id"])
            if is_uuid_string(old_id):
                continue
            new_id = str(uuid.uuid4())
            while new_id in existing_ids:
                new_id = str(uuid.uuid4())
            migrations[old_id] = new_id
            existing_ids.add(new_id)

        if not migrations:
            return

        connection.execute("PRAGMA foreign_keys = OFF")
        for old_id, new_id in migrations.items():
            connection.execute("UPDATE plants SET id = ? WHERE id = ?", (new_id, old_id))
            connection.execute("UPDATE checkins SET plant_id = ? WHERE plant_id = ?", (new_id, old_id))
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")


def list_plant_rows_for_user(connection: sqlite3.Connection, user_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM plants
        WHERE user_id = ?
        ORDER BY datetime(updated_at) DESC, name ASC
        """,
        (user_id,),
    ).fetchall()


def fetch_plant_row(
    connection: sqlite3.Connection,
    plant_id: str,
    *,
    user_id: str | None = None,
) -> sqlite3.Row:
    if user_id:
        row = connection.execute(
            "SELECT * FROM plants WHERE id = ? AND user_id = ?",
            (plant_id, user_id),
        ).fetchone()
    else:
        row = connection.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if row is None:
        raise ApiError(404, "Plant not found.")
    return row


def fetch_checkin_row(
    connection: sqlite3.Connection,
    checkin_id: str,
    *,
    user_id: str | None = None,
) -> sqlite3.Row:
    if user_id:
        row = connection.execute(
            """
            SELECT c.*
            FROM checkins c
            JOIN plants p ON p.id = c.plant_id
            WHERE c.id = ? AND p.user_id = ?
            """,
            (checkin_id, user_id),
        ).fetchone()
    else:
        row = connection.execute("SELECT * FROM checkins WHERE id = ?", (checkin_id,)).fetchone()
    if row is None:
        raise ApiError(404, "Diagnosis not found.")
    return row


def list_checkin_rows(connection: sqlite3.Connection, plant_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM checkins
        WHERE plant_id = ?
        ORDER BY datetime(created_at) DESC, id DESC
        """,
        (plant_id,),
    ).fetchall()


def list_watering_rows(connection: sqlite3.Connection, plant_id: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM waterings
        WHERE plant_id = ?
        ORDER BY date(watered_on) DESC, datetime(created_at) DESC, id DESC
        """,
        (plant_id,),
    ).fetchall()


def fetch_watering_row(
    connection: sqlite3.Connection,
    *,
    plant_id: str,
    watered_on: str,
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM waterings WHERE plant_id = ? AND watered_on = ?",
        (plant_id, watered_on),
    ).fetchone()


def fetch_chat_thread_for_plant(
    connection: sqlite3.Connection,
    *,
    plant_id: str,
    user_id: str,
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM chat_threads WHERE plant_id = ? AND user_id = ?",
        (plant_id, user_id),
    ).fetchone()


def fetch_or_create_chat_thread(
    connection: sqlite3.Connection,
    *,
    plant_id: str,
    user_id: str,
) -> sqlite3.Row:
    existing = fetch_chat_thread_for_plant(connection, plant_id=plant_id, user_id=user_id)
    if existing is not None:
        return existing

    created_at = now_iso()
    thread_id = str(uuid.uuid4())
    while connection.execute("SELECT 1 FROM chat_threads WHERE id = ?", (thread_id,)).fetchone():
        thread_id = str(uuid.uuid4())
    create_chat_thread(
        connection,
        thread_id=thread_id,
        user_id=user_id,
        plant_id=plant_id,
        created_at=created_at,
    )
    return fetch_chat_thread_for_plant(connection, plant_id=plant_id, user_id=user_id)


def list_chat_message_rows(
    connection: sqlite3.Connection,
    thread_id: str,
    *,
    limit: int | None = None,
) -> list[sqlite3.Row]:
    if limit is not None and limit > 0:
        return connection.execute(
            """
            SELECT *
            FROM (
                SELECT *
                FROM chat_messages
                WHERE thread_id = ?
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
            )
            ORDER BY datetime(created_at) ASC, id ASC
            """,
            (thread_id, limit),
        ).fetchall()
    return connection.execute(
        """
        SELECT *
        FROM chat_messages
        WHERE thread_id = ?
        ORDER BY datetime(created_at) ASC, id ASC
        """,
        (thread_id,),
    ).fetchall()


def latest_checkin_row(connection: sqlite3.Connection, plant_id: str) -> sqlite3.Row | None:
    rows = list_checkin_rows(connection, plant_id)
    return rows[0] if rows else None


def serialize_checkin(row: sqlite3.Row) -> dict[str, object]:
    photo_url = row["photo_url"]
    return {
        "id": row["id"],
        "plant_id": row["plant_id"],
        "note": row["note"],
        "photo_url": photo_url,
        "thumbnail_url": thumbnail_url_for(photo_url),
        "health_status": row["health_status"],
        "diagnosis_title": row["diagnosis_title"],
        "diagnosis_summary": row["diagnosis_summary"],
        "care_steps": json_loads(row["care_steps_json"], []),
        "created_at": row["created_at"],
    }


def serialize_chat_thread(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "plant_id": row["plant_id"],
        "rolling_summary": str(row["rolling_summary"] or "").strip(),
        "open_questions": json_loads(row["open_questions_json"], []),
        "last_advice": json_loads(row["last_advice_json"], []),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def serialize_chat_message(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "thread_id": row["thread_id"],
        "user_id": row["user_id"],
        "plant_id": row["plant_id"],
        "checkin_id": row["checkin_id"],
        "role": row["role"],
        "body": row["body"],
        "suggested_actions": json_loads(row["suggested_actions_json"], []),
        "watch_signals": json_loads(row["watch_signals_json"], []),
        "created_at": row["created_at"],
    }


def serialize_tip(row: sqlite3.Row) -> dict[str, str] | None:
    body = str(row["tip_body"] or "").strip()
    if not body:
        return None
    title = str(row["tip_title"] or "").strip() or "Care tip"
    source = str(row["tip_source"] or "").strip().lower() or "reference"
    return {
        "title": title,
        "body": body,
        "source": source,
    }


def serialize_plant_summary(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    latest = latest_checkin_row(connection, row["id"])
    latest_payload = serialize_checkin(latest) if latest else None
    photo_url = latest_payload["photo_url"] if latest_payload and latest_payload.get("photo_url") else row["cover_photo_url"]
    thumbnail_url = (
        latest_payload["thumbnail_url"]
        if latest_payload and latest_payload.get("thumbnail_url")
        else thumbnail_url_for(row["cover_photo_url"])
    )
    return {
        "id": row["id"],
        "name": row["name"],
        "species": row["species"],
        "chinese_name": row["chinese_name"],
        "location": row["location"],
        "tip": serialize_tip(row),
        "photo_url": photo_url,
        "thumbnail_url": thumbnail_url,
        "cover_photo_url": row["cover_photo_url"],
        "latest_status": latest_payload["health_status"] if latest_payload else None,
        "latest_title": latest_payload["diagnosis_title"] if latest_payload else None,
        "latest_summary": latest_payload["diagnosis_summary"] if latest_payload else None,
        "checkin_count": connection.execute(
            "SELECT COUNT(*) FROM checkins WHERE plant_id = ?",
            (row["id"],),
        ).fetchone()[0],
        "updated_at": row["updated_at"],
    }


def serialize_plant_detail(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    checkins = [serialize_checkin(checkin_row) for checkin_row in list_checkin_rows(connection, row["id"])]
    watering_rows = list_watering_rows(connection, row["id"])
    watering_dates = [str(watering_row["watered_on"]) for watering_row in watering_rows]
    last_watered_on = watering_dates[0] if watering_dates else None
    summary = serialize_plant_summary(connection, row)
    return {
        **summary,
        "created_at": row["created_at"],
        "checkins": checkins,
        "latest_checkin": checkins[0] if checkins else None,
        "watering_dates": watering_dates,
        "watering_count": len(watering_dates),
        "watered_today": today_date_iso() in set(watering_dates),
        "last_watered_on": last_watered_on,
    }


def make_plant_id(connection: sqlite3.Connection) -> str:
    candidate = str(uuid.uuid4())
    while connection.execute("SELECT 1 FROM plants WHERE id = ?", (candidate,)).fetchone():
        candidate = str(uuid.uuid4())
    return candidate


def update_chat_thread_memory(
    connection: sqlite3.Connection,
    *,
    thread_id: str,
    rolling_summary: str,
    open_questions: list[str],
    last_advice: list[str],
    updated_at: str,
) -> None:
    connection.execute(
        """
        UPDATE chat_threads
        SET rolling_summary = ?, open_questions_json = ?, last_advice_json = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            rolling_summary.strip(),
            json_dumps(open_questions),
            json_dumps(last_advice),
            updated_at,
            thread_id,
        ),
    )
