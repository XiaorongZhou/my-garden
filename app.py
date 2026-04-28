#!/usr/bin/env python3
"""My Garden: a simple mobile-first plant log and photo check-in app."""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import sqlite3
import subprocess
import tempfile
import uuid
from datetime import datetime
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "my_garden.db"
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = ROOT / "uploads"
OPENAI_RESPONSES_URL = os.environ.get("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses")
OPENAI_PLANT_MODEL = os.environ.get("OPENAI_PLANT_MODEL", "gpt-5-mini")
OPENAI_TIMEOUT_SECONDS = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "25"))
SUPPORTED_VISION_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SUPPORTED_VISION_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
HEIC_SUFFIXES = {".heic", ".heif"}
HEIC_MIME_TYPES = {"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"}
DEMO_MAIDENHAIR_ID = "795f41a2-7fc5-4d84-ae13-a71d4f4f22e1"
DEMO_CAT_PALM_ID = "92db1cd8-e07e-4e90-a95d-216f45a6bc42"


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS plants (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                species TEXT NOT NULL,
                location TEXT NOT NULL,
                notes TEXT NOT NULL,
                cover_photo_url TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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


def json_dumps(payload: object) -> str:
    return json.dumps(payload, separators=(",", ":"))


def json_loads(raw: str | None, fallback: object) -> object:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def create_plant(
    connection: sqlite3.Connection,
    *,
    plant_id: str,
    name: str,
    species: str,
    location: str,
    notes: str,
    cover_photo_url: str | None,
    created_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO plants (
            id, name, species, location, notes, cover_photo_url, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (plant_id, name, species, location, notes, cover_photo_url, created_at, created_at),
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


def ensure_demo_seeded() -> None:
    with get_conn() as connection:
        plant_count = connection.execute("SELECT COUNT(*) FROM plants").fetchone()[0]
        if plant_count:
            return

        now = now_iso()
        create_plant(
            connection,
            plant_id=DEMO_MAIDENHAIR_ID,
            name="Maidenhair Fern",
            species="Adiantum raddianum",
            location="Bathroom shelf",
            notes="Gets crispy quickly when the air feels dry.",
            cover_photo_url="/static/demo/maidenhair-2.jpeg",
            created_at=now,
        )
        create_plant(
            connection,
            plant_id=DEMO_CAT_PALM_ID,
            name="Cat Palm",
            species="Chamaedorea cataractarum",
            location="Living room corner",
            notes="Likes even moisture and brighter mornings.",
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


def fetch_plant_row(connection: sqlite3.Connection, plant_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM plants WHERE id = ?", (plant_id,)).fetchone()
    if row is None:
        raise ApiError(HTTPStatus.NOT_FOUND, "Plant not found.")
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


def latest_checkin_row(connection: sqlite3.Connection, plant_id: str) -> sqlite3.Row | None:
    rows = list_checkin_rows(connection, plant_id)
    return rows[0] if rows else None


def serialize_checkin(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "plant_id": row["plant_id"],
        "note": row["note"],
        "photo_url": row["photo_url"],
        "health_status": row["health_status"],
        "diagnosis_title": row["diagnosis_title"],
        "diagnosis_summary": row["diagnosis_summary"],
        "care_steps": json_loads(row["care_steps_json"], []),
        "created_at": row["created_at"],
    }


def serialize_plant_summary(connection: sqlite3.Connection, row: sqlite3.Row) -> dict[str, object]:
    latest = latest_checkin_row(connection, row["id"])
    latest_payload = serialize_checkin(latest) if latest else None
    photo_url = latest_payload["photo_url"] if latest_payload and latest_payload.get("photo_url") else row["cover_photo_url"]
    return {
        "id": row["id"],
        "name": row["name"],
        "species": row["species"],
        "location": row["location"],
        "notes": row["notes"],
        "photo_url": photo_url,
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
    summary = serialize_plant_summary(connection, row)
    return {
        **summary,
        "created_at": row["created_at"],
        "checkins": checkins,
        "latest_checkin": checkins[0] if checkins else None,
    }


def species_profile(species: str) -> dict[str, str]:
    lowered = species.lower()
    if "maidenhair" in lowered or "adiantum" in lowered or "fern" in lowered:
        return {
            "watering": "even moisture",
            "light": "bright indirect light",
            "common_risk": "dry air",
        }
    if "cat palm" in lowered or "chamaedorea" in lowered or "palm" in lowered:
        return {
            "watering": "even watering",
            "light": "soft bright light",
            "common_risk": "dryness",
        }
    if "snake" in lowered or "dracaena" in lowered or "sansevieria" in lowered:
        return {
            "watering": "let the soil dry between waterings",
            "light": "medium to bright indirect light",
            "common_risk": "overwatering",
        }
    return {
        "watering": "steady, moderate watering",
        "light": "indirect light",
        "common_risk": "watering inconsistency",
    }


def heuristic_plant_identity(*, note: str = "", filename: str = "") -> dict[str, str]:
    text = f"{filename} {note}".lower()
    candidates = [
        (("maidenhair", "adiantum"), ("Maidenhair Fern", "Adiantum raddianum")),
        (("cat palm", "chamaedorea"), ("Cat Palm", "Chamaedorea cataractarum")),
        (("snake plant", "sansevieria", "dracaena trifasciata"), ("Snake Plant", "Dracaena trifasciata")),
        (("pothos", "epipremnum"), ("Pothos", "Epipremnum aureum")),
        (("monstera",), ("Monstera", "Monstera deliciosa")),
        (("philodendron",), ("Philodendron", "Philodendron hederaceum")),
        (("fiddle", "ficus lyrata"), ("Fiddle Leaf Fig", "Ficus lyrata")),
        (("rubber plant", "ficus elastica"), ("Rubber Plant", "Ficus elastica")),
        (("zz plant", "zamioculcas"), ("ZZ Plant", "Zamioculcas zamiifolia")),
        (("spider plant", "chlorophytum"), ("Spider Plant", "Chlorophytum comosum")),
        (("peace lily", "spathiphyllum"), ("Peace Lily", "Spathiphyllum")),
        (("fern",), ("Fern", "Unknown fern")),
        (("palm",), ("Palm", "Unknown palm")),
        (("succulent", "cactus"), ("Succulent", "Unknown succulent")),
    ]
    for tokens, identity in candidates:
        if any(token in text for token in tokens):
            return {
                "name": identity[0],
                "species": identity[1],
                "confidence": "medium",
                "source": "heuristic",
                "caption": "Using a local backup guess from the filename and any notes you added.",
            }
    return {
        "name": "Unknown Houseplant",
        "species": "Unknown houseplant",
        "confidence": "low",
        "source": "heuristic",
        "caption": "We could not confidently identify this one yet, so we are saving a broad houseplant label.",
    }


def openai_api_key() -> str:
    return os.environ.get("OPENAI_API_KEY", "").strip()


def supports_vision_input(*, filename: str = "", content_type: str = "") -> bool:
    if content_type in SUPPORTED_VISION_MIME_TYPES:
        return True
    return Path(filename).suffix.lower() in SUPPORTED_VISION_SUFFIXES


def needs_heic_conversion(*, filename: str = "", content_type: str = "") -> bool:
    if content_type.lower() in HEIC_MIME_TYPES:
        return True
    return Path(filename).suffix.lower() in HEIC_SUFFIXES


def convert_heic_to_jpeg(*, photo_bytes: bytes, filename: str) -> tuple[str, str, bytes]:
    suffix = Path(filename).suffix.lower() or ".heic"
    stem = Path(filename).stem or "upload"
    with tempfile.TemporaryDirectory(prefix="my-garden-heic-") as temp_dir:
        temp_root = Path(temp_dir)
        source_path = temp_root / f"source{suffix}"
        target_path = temp_root / "converted.jpg"
        source_path.write_bytes(photo_bytes)

        try:
            result = subprocess.run(
                ["sips", "-s", "format", "jpeg", str(source_path), "--out", str(target_path)],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("HEIC conversion is not available on this machine.") from exc
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise RuntimeError(f"HEIC conversion failed. {detail[:220]}") from exc

        if not target_path.exists():
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"HEIC conversion did not produce an output image. {detail[:220]}")

        return (f"{stem}.jpg", "image/jpeg", target_path.read_bytes())


def prepare_model_image(*, photo_bytes: bytes, filename: str, content_type: str) -> tuple[str, str, bytes]:
    if needs_heic_conversion(filename=filename, content_type=content_type):
        return convert_heic_to_jpeg(photo_bytes=photo_bytes, filename=filename)
    return (filename, content_type, photo_bytes)


def image_data_url(*, image_bytes: bytes, filename: str = "", content_type: str = "") -> str:
    guessed_type = content_type or mimetypes.guess_type(filename)[0] or "image/jpeg"
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{guessed_type};base64,{encoded}"


def extract_openai_output_text(payload: dict[str, object]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output_items = payload.get("output")
    if not isinstance(output_items, list):
        raise RuntimeError("OpenAI response did not include output text.")

    text_chunks: list[str] = []
    for item in output_items:
        if not isinstance(item, dict):
            continue
        content_items = item.get("content")
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if not isinstance(content, dict):
                continue
            if content.get("type") not in {"output_text", "text"}:
                continue
            text_value = content.get("text")
            if isinstance(text_value, str) and text_value.strip():
                text_chunks.append(text_value)

    if not text_chunks:
        raise RuntimeError("OpenAI response did not include parsable text content.")
    return "\n".join(text_chunks)


def call_openai_structured_output(
    *,
    schema_name: str,
    schema: dict[str, object],
    messages: list[dict[str, object]],
) -> dict[str, object]:
    api_key = openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")

    payload = {
        "model": OPENAI_PLANT_MODEL,
        "input": messages,
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": schema,
            }
        },
    }

    request = urllib_request.Request(
        OPENAI_RESPONSES_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=OPENAI_TIMEOUT_SECONDS) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        raw_error = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI request failed ({exc.code}). {raw_error[:240]}") from exc
    except urllib_error.URLError as exc:
        raise RuntimeError(f"OpenAI request failed. {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI returned invalid JSON. {exc}") from exc

    raw_text = extract_openai_output_text(response_payload)
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI returned non-JSON output. {exc}") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("OpenAI output was not a JSON object.")
    return parsed


def identify_plant_with_model(
    *,
    note: str,
    filename: str,
    content_type: str,
    photo_bytes: bytes,
) -> dict[str, str]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["common_name", "species", "confidence", "caption"],
        "properties": {
            "common_name": {"type": "string"},
            "species": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "caption": {"type": "string"},
        },
    }
    system_prompt = (
        "You identify common houseplants from a single photo and a short owner note. "
        "Return conservative JSON only. Prefer honest, broad labels over overconfident specificity. "
        "If the species is unclear, use a broader common name like Fern or Palm, or Unknown Houseplant."
    )
    note_text = note.strip() or "No owner note."
    filename_text = filename.strip() or "Unnamed upload."
    messages = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Identify this plant for a personal plant log.\n"
                        f"Owner note: {note_text}\n"
                        f"Filename: {filename_text}\n"
                        "Return a human-friendly common name, a likely Latin species if you can support it, "
                        "a confidence value, and a short caption the app can show to the user."
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": image_data_url(
                        image_bytes=photo_bytes,
                        filename=filename,
                        content_type=content_type,
                    ),
                    "detail": "high",
                },
            ],
        },
    ]
    parsed = call_openai_structured_output(
        schema_name="plant_identity",
        schema=schema,
        messages=messages,
    )
    name = str(parsed.get("common_name") or "").strip() or "Unknown Houseplant"
    species = str(parsed.get("species") or "").strip() or "Unknown houseplant"
    confidence = str(parsed.get("confidence") or "low").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    caption = str(parsed.get("caption") or "").strip() or "Identified from the photo you added."
    return {
        "name": name,
        "species": species,
        "confidence": confidence,
        "source": "openai",
        "caption": caption,
    }


def normalize_diagnosis_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise RuntimeError("Diagnosis payload was not an object.")
    health_status = str(payload.get("health_status") or "watch").strip().lower()
    if health_status not in {"thriving", "watch", "needs_care"}:
        health_status = "watch"
    diagnosis_title = str(payload.get("diagnosis_title") or "").strip() or "Nothing alarming stands out yet"
    diagnosis_summary = str(payload.get("diagnosis_summary") or "").strip()
    care_steps = [str(step).strip() for step in payload.get("care_steps") or [] if str(step).strip()][:3]
    return {
        "health_status": health_status,
        "diagnosis_title": diagnosis_title,
        "diagnosis_summary": diagnosis_summary,
        "care_steps": care_steps,
    }


def preview_new_plant_with_model(
    *,
    note: str,
    filename: str,
    content_type: str,
    photo_bytes: bytes,
) -> dict[str, object]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "common_name",
            "species",
            "confidence",
            "caption",
            "health_status",
            "diagnosis_title",
            "diagnosis_summary",
            "care_steps",
        ],
        "properties": {
            "common_name": {"type": "string"},
            "species": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "caption": {"type": "string"},
            "health_status": {"type": "string", "enum": ["thriving", "watch", "needs_care"]},
            "diagnosis_title": {"type": "string"},
            "diagnosis_summary": {"type": "string"},
            "care_steps": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
        },
    }
    system_prompt = (
        "You are helping a plant care app onboard a new plant from one photo. "
        "First identify the plant conservatively. Then provide an initial health read. "
        "Return strict JSON only. Prefer honest, broad labels over overconfident specificity. "
        "If the species is unclear, use a broader common name like Fern or Palm, or Unknown Houseplant. "
        "If the health read is uncertain, say that clearly and avoid dramatic claims."
    )
    note_text = note.strip() or "No owner note."
    filename_text = filename.strip() or "Unnamed upload."
    messages = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "This is a new plant being added to a personal plant log.\n"
                        f"Owner note: {note_text}\n"
                        f"Filename: {filename_text}\n"
                        "Return:\n"
                        "- common_name: a human-friendly plant name\n"
                        "- species: the likely Latin species if supported, otherwise a broad label\n"
                        "- confidence: high, medium, or low\n"
                        "- caption: one short line the app can show\n"
                        "- health_status: thriving, watch, or needs_care\n"
                        "- diagnosis_title: a short title for the first read\n"
                        "- diagnosis_summary: a concise 1-2 sentence initial diagnosis\n"
                        "- care_steps: 0-3 concrete next actions"
                    ),
                },
                {
                    "type": "input_image",
                    "image_url": image_data_url(
                        image_bytes=photo_bytes,
                        filename=filename,
                        content_type=content_type,
                    ),
                    "detail": "high",
                },
            ],
        },
    ]
    parsed = call_openai_structured_output(
        schema_name="plant_intake_preview",
        schema=schema,
        messages=messages,
    )
    suggestion = {
        "name": str(parsed.get("common_name") or "").strip() or "Unknown Houseplant",
        "species": str(parsed.get("species") or "").strip() or "Unknown houseplant",
        "confidence": str(parsed.get("confidence") or "low").strip().lower(),
        "source": "openai",
        "caption": str(parsed.get("caption") or "").strip() or "Identified from the photo you added.",
    }
    if suggestion["confidence"] not in {"high", "medium", "low"}:
        suggestion["confidence"] = "low"
    diagnosis = normalize_diagnosis_payload(parsed)
    return {
        "suggestion": suggestion,
        "diagnosis": diagnosis,
    }


def build_add_preview(
    *,
    note: str = "",
    filename: str = "",
    content_type: str = "",
    photo_bytes: bytes | None = None,
) -> dict[str, object]:
    suggestion = heuristic_plant_identity(note=note, filename=filename)
    diagnosis = heuristic_diagnosis({"species": suggestion["species"], "notes": note}, note, bool(photo_bytes))
    preview = {"suggestion": suggestion, "diagnosis": diagnosis}

    if not photo_bytes:
        return preview
    try:
        model_filename, model_content_type, model_bytes = prepare_model_image(
            photo_bytes=photo_bytes,
            filename=filename,
            content_type=content_type,
        )
    except RuntimeError:
        suggestion["caption"] = "This photo format could not be prepared for live plant ID, so we used a local backup guess."
        return preview
    if not supports_vision_input(filename=model_filename, content_type=model_content_type):
        suggestion["caption"] = "This photo format is not supported by the live vision model yet, so we used a local backup guess."
        return preview
    if not openai_api_key():
        suggestion["caption"] = "Using the local backup guess for now. Add an OpenAI API key to enable photo-based plant ID."
        return preview
    try:
        return preview_new_plant_with_model(
            note=note,
            filename=model_filename,
            content_type=model_content_type,
            photo_bytes=model_bytes,
        )
    except RuntimeError:
        suggestion["caption"] = "The live plant ID model was unavailable, so we fell back to the local guess."
        return preview


def infer_plant_identity(
    *,
    note: str = "",
    filename: str = "",
    content_type: str = "",
    photo_bytes: bytes | None = None,
) -> dict[str, str]:
    fallback = heuristic_plant_identity(note=note, filename=filename)
    if not photo_bytes:
        return fallback
    try:
        model_filename, model_content_type, model_bytes = prepare_model_image(
            photo_bytes=photo_bytes,
            filename=filename,
            content_type=content_type,
        )
    except RuntimeError:
        fallback["caption"] = "This photo format could not be prepared for live plant ID, so we used a local backup guess."
        return fallback
    if not supports_vision_input(filename=model_filename, content_type=model_content_type):
        fallback["caption"] = (
            "This photo format is not supported by the live vision model yet, so we used a local backup guess."
        )
        return fallback
    if not openai_api_key():
        fallback["caption"] = "Using the local backup guess for now. Add an OpenAI API key to enable photo-based plant ID."
        return fallback
    try:
        return identify_plant_with_model(
            note=note,
            filename=model_filename,
            content_type=model_content_type,
            photo_bytes=model_bytes,
        )
    except RuntimeError:
        fallback["caption"] = "The live plant ID model was unavailable, so we fell back to the local guess."
        return fallback


def contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def heuristic_diagnosis(plant: sqlite3.Row, note: str, has_photo: bool) -> dict[str, object]:
    profile = species_profile(plant["species"])
    combined = " ".join(fragment for fragment in (plant["notes"], note) if fragment).lower()

    if contains_any(combined, ("bugs", "mites", "webbing", "spots", "pests", "fungus", "mold")):
        return {
            "health_status": "needs_care",
            "diagnosis_title": "Check the leaves before changing watering",
            "diagnosis_summary": "Pest-like or surface damage signals are more important to inspect first than adjusting water right away.",
            "care_steps": [
                "Inspect the underside of the leaves with bright light.",
                "Isolate the plant if you see active pests.",
                "Take a second close-up photo after your inspection.",
            ],
        }

    if contains_any(combined, ("yellow", "yellowing", "mushy", "soggy", "soft stem", "wet soil", "overwater")):
        return {
            "health_status": "needs_care",
            "diagnosis_title": "Too much water is a real possibility",
            "diagnosis_summary": "Yellowing or soggy language usually points to root stress, so let the soil dry down before another watering.",
            "care_steps": [
                "Pause watering until the top layer dries out.",
                "Make sure excess water can drain freely.",
                "Watch for any soft stems or spreading yellow leaves.",
            ],
        }

    if contains_any(combined, ("repot", "rootbound", "roots", "crowded pot", "circling roots")):
        return {
            "health_status": "watch",
            "diagnosis_title": "It may be getting cramped in the pot",
            "diagnosis_summary": "The plant sounds ready for a root check, but you can confirm before committing to a repot.",
            "care_steps": [
                "Peek at the root ball this weekend.",
                "Repot only if roots are tightly circling.",
                "Keep the watering routine steady in the meantime.",
            ],
        }

    if contains_any(combined, ("dark", "dim", "low light", "far from window", "leaning", "leggy")):
        return {
            "health_status": "watch",
            "diagnosis_title": "Light may be part of the problem",
            "diagnosis_summary": "This sounds more like a placement issue than an emergency. A small move toward brighter indirect light may help.",
            "care_steps": [
                f"Move it toward {profile['light']}.",
                "Rotate the pot a quarter turn.",
                "Do another photo check-in after two days in the new spot.",
            ],
        }

    if contains_any(combined, ("crispy", "crisp", "brown tips", "dry air", "curl", "curling")):
        return {
            "health_status": "watch",
            "diagnosis_title": "The plant looks sensitive to dry air",
            "diagnosis_summary": f"The note fits {profile['common_risk']} more than a major watering mistake right now.",
            "care_steps": [
                "Hold steady instead of doubling the watering.",
                "Keep it away from vents or especially dry corners.",
                "Check whether the leaves soften within a day or two.",
            ],
        }

    if contains_any(combined, ("droop", "droopy", "wilt", "wilting", "dry soil", "topsoil dry", "thirsty")):
        return {
            "health_status": "needs_care",
            "diagnosis_title": "This one likely needs a drink",
            "diagnosis_summary": "Droop plus dry-soil language usually points to ordinary thirst, especially if the rest of the plant is still intact.",
            "care_steps": [
                f"Water it with a full, even pass that matches {profile['watering']}.",
                "Let extra water drain fully.",
                "Take another photo tomorrow to confirm the leaves perk back up.",
            ],
        }

    if note.strip():
        return {
            "health_status": "thriving",
            "diagnosis_title": "Nothing alarming stands out yet",
            "diagnosis_summary": "Your note does not suggest a major stress pattern. Keep the routine steady and watch for change instead of overcorrecting.",
            "care_steps": [
                f"Keep giving it {profile['light']}.",
                f"Stick with {profile['watering']}.",
                "Log another check-in if the leaves start changing quickly.",
            ],
        }

    if has_photo:
        return {
            "health_status": "watch",
            "diagnosis_title": "Photo saved. Add one quick observation next time",
            "diagnosis_summary": "I saved the photo, but I still need one quick observation next time to make the diagnosis specific.",
            "care_steps": [],
        }

    return {
        "health_status": "watch",
        "diagnosis_title": "Add a little more context",
        "diagnosis_summary": "A short note about dryness, color, or leaf posture will make the diagnosis much more useful.",
        "care_steps": [
            "Add a plant photo.",
            "Describe what looks different today.",
            "Try the check-in again.",
        ],
    }


def diagnose_plant_with_model(
    *,
    plant: sqlite3.Row,
    note: str,
    filename: str = "",
    content_type: str = "",
    photo_bytes: bytes | None = None,
) -> dict[str, object]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["health_status", "diagnosis_title", "diagnosis_summary", "care_steps"],
        "properties": {
            "health_status": {"type": "string", "enum": ["thriving", "watch", "needs_care"]},
            "diagnosis_title": {"type": "string"},
            "diagnosis_summary": {"type": "string"},
            "care_steps": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
        },
    }

    system_prompt = (
        "You diagnose the health of an already-identified plant for a plant care app. "
        "The plant name and species are given to you as context. "
        "Do not identify or rename the plant. Do not guess a different species. "
        "Focus only on health status, likely issue, and the next most useful actions. "
        "Be conservative. If the photo or note is insufficient for a confident diagnosis, say that clearly."
    )

    note_text = note.strip() or "No new owner note."
    saved_notes = str(plant["notes"] or "").strip() or "No saved plant notes."
    messages: list[dict[str, object]] = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": system_prompt}],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Diagnose this existing plant check-in.\n"
                        f"Plant name: {plant['name']}\n"
                        f"Known species: {plant['species']}\n"
                        f"Location: {plant['location'] or 'Home'}\n"
                        f"Saved plant notes: {saved_notes}\n"
                        f"Today's owner note: {note_text}\n"
                        "Return JSON only.\n"
                        "Use the known plant identity as fixed context.\n"
                        "Do not identify the plant again.\n"
                        "Do not suggest a new species.\n"
                        "Provide:\n"
                        "- health_status: thriving, watch, or needs_care\n"
                        "- diagnosis_title: a short title\n"
                        "- diagnosis_summary: a concise 1-2 sentence diagnosis\n"
                        "- care_steps: 0-3 concrete next actions for the next few days"
                    ),
                }
            ],
        },
    ]

    if photo_bytes:
        messages[1]["content"].append(
            {
                "type": "input_image",
                "image_url": image_data_url(
                    image_bytes=photo_bytes,
                    filename=filename,
                    content_type=content_type,
                ),
                "detail": "high",
            }
        )

    parsed = call_openai_structured_output(
        schema_name="plant_diagnosis",
        schema=schema,
        messages=messages,
    )
    return normalize_diagnosis_payload(parsed)


def diagnose_plant(
    *,
    plant: sqlite3.Row,
    note: str,
    has_photo: bool,
    filename: str = "",
    content_type: str = "",
    photo_bytes: bytes | None = None,
) -> dict[str, object]:
    if openai_api_key() and (note.strip() or photo_bytes):
        try:
            model_filename = filename
            model_content_type = content_type
            model_bytes = photo_bytes
            if photo_bytes:
                model_filename, model_content_type, model_bytes = prepare_model_image(
                    photo_bytes=photo_bytes,
                    filename=filename,
                    content_type=content_type,
                )
                if not supports_vision_input(filename=model_filename, content_type=model_content_type):
                    raise RuntimeError("Prepared image format is not supported for diagnosis.")
            return diagnose_plant_with_model(
                plant=plant,
                note=note,
                filename=model_filename,
                content_type=model_content_type,
                photo_bytes=model_bytes,
            )
        except RuntimeError:
            pass

    return heuristic_diagnosis(plant, note, has_photo)


def make_plant_id(connection: sqlite3.Connection) -> str:
    candidate = str(uuid.uuid4())
    while connection.execute("SELECT 1 FROM plants WHERE id = ?", (candidate,)).fetchone():
        candidate = str(uuid.uuid4())
    return candidate


def decode_body(handler: BaseHTTPRequestHandler) -> bytes:
    length = int(handler.headers.get("Content-Length", "0"))
    return handler.rfile.read(length) if length > 0 else b""


def parse_json_body(handler: BaseHTTPRequestHandler) -> dict[str, object]:
    raw = decode_body(handler)
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"Invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ApiError(HTTPStatus.BAD_REQUEST, "JSON payload must be an object.")
    return payload


def parse_multipart(handler: BaseHTTPRequestHandler) -> tuple[dict[str, str], dict[str, list[dict[str, object]]]]:
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Expected multipart/form-data.")

    raw = decode_body(handler)
    headers = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8")
    message = BytesParser(policy=default).parsebytes(headers + raw)

    fields: dict[str, str] = {}
    files: dict[str, list[dict[str, object]]] = {}
    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        name = part.get_param("name", header="content-disposition") or ""
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            files.setdefault(name, []).append(
                {
                    "filename": filename,
                    "content_type": part.get_content_type(),
                    "bytes": payload,
                }
            )
            continue
        charset = part.get_content_charset("utf-8")
        fields[name] = payload.decode(charset, errors="replace")
    return fields, files


def pick_file(files: dict[str, list[dict[str, object]]]) -> dict[str, object] | None:
    for key in ("photo", "image", "photos[]", "photos", "file"):
        if files.get(key):
            return files[key][0]
    for candidates in files.values():
        if candidates:
            return candidates[0]
    return None


def safe_upload_suffix(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".heic"}:
        return suffix
    return ".jpg"


def store_upload(file_payload: dict[str, object], *, prefix: str) -> str:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    suffix = safe_upload_suffix(str(file_payload.get("filename") or "upload.jpg"))
    name = f"{prefix}-{uuid.uuid4().hex[:10]}{suffix}"
    path = UPLOAD_DIR / name
    path.write_bytes(file_payload.get("bytes", b""))
    return f"/uploads/{name}"


def upload_token_from_url(photo_url: str | None) -> str:
    if not photo_url or not photo_url.startswith("/uploads/"):
        return ""
    return photo_url.rsplit("/", 1)[-1]


def photo_url_from_upload_token(token: str) -> str | None:
    cleaned = str(token or "").strip()
    if not cleaned:
        return None
    path = safe_child(UPLOAD_DIR, cleaned)
    if not path.exists() or not path.is_file():
        raise ApiError(HTTPStatus.BAD_REQUEST, "Uploaded photo could not be found. Please add the photo again.")
    return f"/uploads/{cleaned}"


def maybe_delete_upload(photo_url: str | None) -> None:
    if not photo_url or not photo_url.startswith("/uploads/"):
        return
    relative = photo_url[len("/uploads/") :]
    path = safe_child(UPLOAD_DIR, relative)
    if path.exists() and path.is_file():
        path.unlink()


def safe_child(root: Path, raw_relative_path: str) -> Path:
    candidate = (root / raw_relative_path).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid path.")
    return candidate


def content_type_for(path: Path) -> str:
    if path.suffix == ".webmanifest":
        return "application/manifest+json"
    if path.suffix == ".svg":
        return "image/svg+xml"
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed or "application/octet-stream"


class MyGardenHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type_for(path))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_api_error(self, exc: ApiError) -> None:
        self._send_json({"error": exc.message}, status=exc.status)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/":
                return self._send_file(STATIC_DIR / "index.html")

            if path in {
                "/manifest.webmanifest",
                "/sw.js",
                "/apple-touch-icon.png",
                "/icon-192.png",
                "/icon-512.png",
                "/maskable-icon-512.png",
            }:
                return self._send_file(STATIC_DIR / path.lstrip("/"))

            if path.startswith("/static/"):
                relative = unquote(path[len("/static/") :])
                return self._send_file(safe_child(STATIC_DIR, relative))

            if path.startswith("/uploads/"):
                relative = unquote(path[len("/uploads/") :])
                return self._send_file(safe_child(UPLOAD_DIR, relative))

            if path == "/api/plants":
                with get_conn() as connection:
                    rows = connection.execute(
                        "SELECT * FROM plants ORDER BY datetime(updated_at) DESC, name ASC"
                    ).fetchall()
                    payload = {"plants": [serialize_plant_summary(connection, row) for row in rows]}
                return self._send_json(payload)

            plant_match = re.fullmatch(r"/api/plants/([^/]+)", path)
            if plant_match:
                plant_id = plant_match.group(1)
                with get_conn() as connection:
                    row = fetch_plant_row(connection, plant_id)
                    payload = {"plant": serialize_plant_detail(connection, row)}
                return self._send_json(payload)

            raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")
        except ApiError as exc:
            self._send_api_error(exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/plant-identity-preview":
                fields, files = parse_multipart(self)
                file_payload = pick_file(files)
                if not file_payload:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Add a plant photo first.")
                note = str(fields.get("notes") or fields.get("note") or "").strip()
                preview_photo_url = store_upload(file_payload, prefix="preview")
                preview = build_add_preview(
                    note=note,
                    filename=str(file_payload.get("filename") or ""),
                    content_type=str(file_payload.get("content_type") or ""),
                    photo_bytes=bytes(file_payload.get("bytes") or b""),
                )
                return self._send_json(
                    {
                        **preview,
                        "upload_token": upload_token_from_url(preview_photo_url),
                    }
                )

            if path == "/api/plants":
                content_type = self.headers.get("Content-Type", "")

                if "application/json" in content_type:
                    payload = parse_json_body(self)
                    notes = str(payload.get("notes") or "").strip()
                    suggestion = infer_plant_identity(note=notes, filename="")
                    name = str(payload.get("name") or "").strip() or suggestion["name"]
                    species = str(payload.get("species") or "").strip() or suggestion["species"]
                    location = str(payload.get("location") or "").strip() or "Home"
                    photo_url = None
                    initial_note = ""
                    file_payload = None
                    raw_diagnosis = payload.get("diagnosis_payload") or payload.get("diagnosis")
                    raw_upload_token = payload.get("upload_token") or ""
                else:
                    fields, files = parse_multipart(self)
                    file_payload = pick_file(files)
                    raw_upload_token = fields.get("upload_token") or ""
                    photo_url = store_upload(file_payload, prefix="plant") if file_payload else None
                    if not photo_url and raw_upload_token:
                        photo_url = photo_url_from_upload_token(str(raw_upload_token))
                    notes = str(fields.get("notes") or fields.get("note") or "").strip()
                    initial_note = notes
                    location = str(fields.get("location") or "").strip() or "Home"
                    suggestion = infer_plant_identity(
                        note=notes,
                        filename=str(file_payload.get("filename") or "") if file_payload else "",
                        content_type=str(file_payload.get("content_type") or "") if file_payload else "",
                        photo_bytes=bytes(file_payload.get("bytes") or b"") if file_payload else None,
                    )
                    name = str(fields.get("name") or "").strip() or suggestion["name"]
                    species = str(fields.get("species") or "").strip() or suggestion["species"]
                    raw_diagnosis = fields.get("diagnosis_payload") or ""

                if not photo_url and raw_upload_token:
                    photo_url = photo_url_from_upload_token(str(raw_upload_token))

                provided_diagnosis = None
                if isinstance(raw_diagnosis, dict):
                    try:
                        provided_diagnosis = normalize_diagnosis_payload(raw_diagnosis)
                    except RuntimeError:
                        provided_diagnosis = None
                elif isinstance(raw_diagnosis, str) and raw_diagnosis.strip():
                    try:
                        provided_diagnosis = normalize_diagnosis_payload(json.loads(raw_diagnosis))
                    except (json.JSONDecodeError, RuntimeError):
                        provided_diagnosis = None

                with get_conn() as connection:
                    plant_id = make_plant_id(connection)
                    created_at = now_iso()
                    create_plant(
                        connection,
                        plant_id=plant_id,
                        name=name,
                        species=species,
                        location=location,
                        notes=notes,
                        cover_photo_url=photo_url,
                        created_at=created_at,
                    )
                    created_checkin = None
                    if photo_url or initial_note:
                        plant_row = fetch_plant_row(connection, plant_id)
                        diagnosis = provided_diagnosis or heuristic_diagnosis(
                            plant_row,
                            initial_note,
                            photo_url is not None,
                        )
                        checkin_id = f"{plant_id}-{uuid.uuid4().hex[:10]}"
                        create_checkin(
                            connection,
                            checkin_id=checkin_id,
                            plant_id=plant_id,
                            note=initial_note,
                            photo_url=photo_url,
                            health_status=str(diagnosis["health_status"]),
                            diagnosis_title=str(diagnosis["diagnosis_title"]),
                            diagnosis_summary=str(diagnosis["diagnosis_summary"]),
                            care_steps=list(diagnosis["care_steps"]),
                            created_at=created_at,
                        )
                        created_checkin = latest_checkin_row(connection, plant_id)
                    row = fetch_plant_row(connection, plant_id)
                    payload_out = {
                        "plant": serialize_plant_detail(connection, row),
                        "checkin": serialize_checkin(created_checkin) if created_checkin else None,
                        "identity": suggestion,
                    }
                    connection.commit()
                return self._send_json(payload_out, status=201)

            checkin_match = re.fullmatch(r"/api/plants/([^/]+)/checkins", path)
            if checkin_match:
                plant_id = checkin_match.group(1)
                content_type = self.headers.get("Content-Type", "")

                if "application/json" in content_type:
                    payload = parse_json_body(self)
                    note = str(payload.get("note") or "").strip()
                    photo_url = None
                    file_payload = None
                else:
                    fields, files = parse_multipart(self)
                    note = str(fields.get("note") or "").strip()
                    file_payload = pick_file(files)
                    photo_url = store_upload(file_payload, prefix=plant_id) if file_payload else None

                if not note and not photo_url:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Add a photo or a note for this check-in.")

                with get_conn() as connection:
                    plant = fetch_plant_row(connection, plant_id)
                    diagnosis = diagnose_plant(
                        plant=plant,
                        note=note,
                        has_photo=photo_url is not None,
                        filename=str(file_payload.get("filename") or "") if file_payload else "",
                        content_type=str(file_payload.get("content_type") or "") if file_payload else "",
                        photo_bytes=bytes(file_payload.get("bytes") or b"") if file_payload else None,
                    )
                    checkin_id = f"{plant_id}-{uuid.uuid4().hex[:10]}"
                    created_at = now_iso()
                    create_checkin(
                        connection,
                        checkin_id=checkin_id,
                        plant_id=plant_id,
                        note=note,
                        photo_url=photo_url,
                        health_status=str(diagnosis["health_status"]),
                        diagnosis_title=str(diagnosis["diagnosis_title"]),
                        diagnosis_summary=str(diagnosis["diagnosis_summary"]),
                        care_steps=list(diagnosis["care_steps"]),
                        created_at=created_at,
                    )
                    if photo_url and not plant["cover_photo_url"]:
                        connection.execute(
                            "UPDATE plants SET cover_photo_url = ?, updated_at = ? WHERE id = ?",
                            (photo_url, created_at, plant_id),
                        )
                    row = fetch_plant_row(connection, plant_id)
                    latest = latest_checkin_row(connection, plant_id)
                    payload_out = {
                        "plant": serialize_plant_detail(connection, row),
                        "checkin": serialize_checkin(latest) if latest else None,
                    }
                    connection.commit()
                return self._send_json(payload_out, status=201)

            raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")
        except ApiError as exc:
            self._send_api_error(exc)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            plant_match = re.fullmatch(r"/api/plants/([^/]+)", path)
            if not plant_match:
                raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")

            plant_id = plant_match.group(1)
            with get_conn() as connection:
                row = fetch_plant_row(connection, plant_id)
                checkin_rows = list_checkin_rows(connection, plant_id)
                upload_urls = [row["cover_photo_url"]]
                upload_urls.extend(checkin_row["photo_url"] for checkin_row in checkin_rows)

                connection.execute("DELETE FROM checkins WHERE plant_id = ?", (plant_id,))
                connection.execute("DELETE FROM plants WHERE id = ?", (plant_id,))
                connection.commit()

            for upload_url in upload_urls:
                maybe_delete_upload(upload_url)

            return self._send_json({"deleted": True, "plant_id": plant_id})
        except ApiError as exc:
            self._send_api_error(exc)


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    ensure_demo_seeded()
    migrate_plant_ids_to_uuid()
    normalize_legacy_checkins()
    try:
        server = ThreadingHTTPServer((host, port), MyGardenHandler)
    except OSError as exc:
        print(f"Failed to bind server on {host}:{port}: {exc}")
        print("Try a different port, e.g. PORT=8030 python3 app.py")
        raise
    print(f"Serving My Garden on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_server(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )
