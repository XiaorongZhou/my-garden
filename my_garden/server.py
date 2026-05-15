from __future__ import annotations

import json
import re
import uuid
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from .config import ADMIN_EMAILS, SESSION_TTL_DAYS, STATIC_DIR, UPLOAD_DIR
from .data import (
    admin_metrics,
    create_user_session,
    create_or_claim_user,
    create_chat_message,
    create_checkin,
    create_plant,
    create_watering_event,
    ensure_demo_seeded,
    fetch_checkin_row,
    fetch_chat_thread_for_plant,
    fetch_or_create_chat_thread,
    fetch_plant_row,
    first_registered_user_id,
    fetch_user_by_session_token,
    fetch_watering_row,
    get_conn,
    has_claimable_user,
    init_db,
    latest_checkin_row,
    list_chat_message_rows,
    list_checkin_rows,
    list_plant_rows_for_user,
    make_plant_id,
    migrate_plant_ids_to_uuid,
    normalize_legacy_checkins,
    now_iso,
    serialize_chat_message,
    serialize_chat_thread,
    serialize_checkin,
    serialize_plant_detail,
    serialize_plant_summary,
    serialize_user,
    today_date_iso,
    update_chat_thread_memory,
)
from .errors import ApiError
from .http_utils import (
    content_type_for,
    maybe_delete_upload,
    parse_json_body,
    parse_multipart,
    photo_url_from_upload_token,
    pick_file,
    safe_child,
    static_index_path,
    store_thumbnail,
    store_upload,
    upload_token_from_url,
)
from .ai_providers import model_runtime_summary
from .limits import consume_ai_quota
from .plant_ai import (
    answer_plant_followup,
    build_add_preview,
    default_tip_for_identity,
    diagnose_plant,
    followup_prompt_suggestions,
    heuristic_diagnosis,
    heuristic_chinese_name,
    infer_plant_identity,
    normalize_diagnosis_payload,
)

LOCAL_TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?")
SESSION_COOKIE_NAME = "my_garden_session"


def client_created_at_or_now(value: object) -> str:
    candidate = str(value or "").strip()
    if LOCAL_TIMESTAMP_RE.fullmatch(candidate):
        return candidate if len(candidate) == 19 else f"{candidate}:00"
    return now_iso()


def session_cookie_header(session_token: str) -> str:
    max_age = max(1, SESSION_TTL_DAYS) * 24 * 60 * 60
    return (
        f"{SESSION_COOKIE_NAME}={session_token}; Path=/; Max-Age={max_age}; "
        "SameSite=Lax; HttpOnly"
    )


def is_admin_user(connection, user_row) -> bool:
    if user_row is None:
        return False
    normalized_email = str(user_row["normalized_email"] or user_row["email"] or "").strip().lower()
    if ADMIN_EMAILS:
        return normalized_email in ADMIN_EMAILS
    return str(user_row["id"]) == first_registered_user_id(connection)


class MyGardenHandler(BaseHTTPRequestHandler):
    def _send_json(
        self,
        payload: dict[str, object],
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path) -> None:
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

    def _current_session_token(self) -> str:
        auth_header = str(self.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        header_token = str(self.headers.get("X-My-Garden-Session") or "").strip()
        if header_token:
            return header_token
        cookie_header = str(self.headers.get("Cookie") or "")
        if cookie_header:
            cookie = SimpleCookie()
            cookie.load(cookie_header)
            morsel = cookie.get(SESSION_COOKIE_NAME)
            if morsel is not None:
                return str(morsel.value or "").strip()
        return ""

    def _resolve_current_user(self, connection, *, required: bool = True):
        token = self._current_session_token()
        if not token:
            if required:
                raise ApiError(401, "Sign in to open your garden.")
            return None
        user = fetch_user_by_session_token(connection, token)
        if user is None and required:
            raise ApiError(401, "Your session expired. Please sign in again.")
        return user

    def _consume_ai_quota(self, user_id: str, action: str) -> None:
        with get_conn() as connection:
            consume_ai_quota(connection, user_id=user_id, action=action)
            connection.commit()

    def _identity_from_provided_values(
        self,
        *,
        name: str,
        species: str,
        chinese_name: str,
    ) -> dict[str, str]:
        return {
            "name": name,
            "species": species,
            "chinese_name": chinese_name,
            "confidence": "user",
            "source": "provided",
            "caption": "Using the plant details saved from your identification step.",
        }

    def _session_payload(
        self,
        connection,
        user_row=None,
        *,
        claimed_legacy_garden: bool = False,
        session_token: str = "",
        password_was_set: bool = False,
    ):
        return {
            "user": serialize_user(user_row) if user_row is not None else None,
            "is_admin": is_admin_user(connection, user_row) if user_row is not None else False,
            "session_token": session_token,
            "claimable_legacy_garden": has_claimable_user(connection),
            "claimed_legacy_garden": claimed_legacy_garden,
            "password_was_set": password_was_set,
        }

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/":
                return self._send_file(static_index_path())

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

            if path == "/api/session":
                with get_conn() as connection:
                    user = self._resolve_current_user(connection, required=False)
                    return self._send_json(self._session_payload(connection, user))

            if path == "/api/admin/metrics":
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    if not is_admin_user(connection, user):
                        raise ApiError(HTTPStatus.FORBIDDEN, "Admin access required.")
                    return self._send_json({"metrics": admin_metrics(connection)})

            if path == "/api/plants":
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    rows = list_plant_rows_for_user(connection, str(user["id"]))
                    payload = {"plants": [serialize_plant_summary(connection, row) for row in rows]}
                return self._send_json(payload)

            chat_match = re.fullmatch(r"/api/plants/([^/]+)/chat", path)
            if chat_match:
                plant_id = chat_match.group(1)
                requested_checkin_id = parse_qs(parsed.query).get("checkin_id", [None])[0]
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    thread = fetch_or_create_chat_thread(
                        connection,
                        plant_id=plant_id,
                        user_id=str(user["id"]),
                    )
                    latest = latest_checkin_row(connection, plant_id)
                    focused_checkin = None
                    if requested_checkin_id:
                        focused_row = fetch_checkin_row(
                            connection,
                            str(requested_checkin_id),
                            user_id=str(user["id"]),
                        )
                        if str(focused_row["plant_id"]) != plant_id:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "That diagnosis belongs to a different plant.")
                        focused_checkin = serialize_checkin(focused_row)
                    payload = {
                        "plant": {
                            **serialize_plant_summary(connection, row),
                            "latest_checkin": serialize_checkin(latest) if latest else None,
                        },
                        "thread": serialize_chat_thread(thread),
                        "messages": [
                            serialize_chat_message(message_row)
                            for message_row in list_chat_message_rows(connection, str(thread["id"]))
                        ],
                        "focused_checkin": focused_checkin,
                        "suggested_prompts": followup_prompt_suggestions(
                            plant=row,
                            latest_checkin=serialize_checkin(latest) if latest else None,
                        ),
                    }
                    connection.commit()
                return self._send_json(payload)

            plant_match = re.fullmatch(r"/api/plants/([^/]+)", path)
            if plant_match:
                plant_id = plant_match.group(1)
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    payload = {"plant": serialize_plant_detail(connection, row)}
                return self._send_json(payload)

            raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")
        except ApiError as exc:
            self._send_api_error(exc)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/api/session":
                payload = parse_json_body(self)
                if not isinstance(payload, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Session payload must be a JSON object.")
                name = str(payload.get("name") or "").strip()
                email = str(payload.get("email") or "").strip()
                password = str(payload.get("password") or "")
                with get_conn() as connection:
                    user, claimed_legacy_garden, password_was_set = create_or_claim_user(
                        connection,
                        name=name,
                        email=email,
                        password=password,
                    )
                    session_token = create_user_session(connection, user_id=str(user["id"]))
                    payload_out = self._session_payload(
                        connection,
                        user,
                        claimed_legacy_garden=claimed_legacy_garden,
                        session_token=session_token,
                        password_was_set=password_was_set,
                    )
                    connection.commit()
                return self._send_json(
                    payload_out,
                    status=201,
                    headers={"Set-Cookie": session_cookie_header(session_token)},
                )

            if path == "/api/plant-identity-preview":
                fields, files = parse_multipart(self)
                file_payload = pick_file(files)
                thumbnail_payload = pick_file(files, field_names=("thumbnail",))
                if not file_payload:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Add a plant photo first.")
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    consume_ai_quota(connection, user_id=str(user["id"]), action="identity")
                    connection.commit()
                note = str(fields.get("notes") or fields.get("note") or "").strip()
                preview_photo_url = store_upload(file_payload, prefix="preview")
                store_thumbnail(thumbnail_payload, photo_url=preview_photo_url)
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
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    user_id = str(user["id"])
                content_type = self.headers.get("Content-Type", "")

                if "application/json" in content_type:
                    payload = parse_json_body(self)
                    notes = str(payload.get("notes") or "").strip()
                    name = str(payload.get("name") or "").strip()
                    species = str(payload.get("species") or "").strip()
                    chinese_name = str(payload.get("chinese_name") or "").strip()
                    if not name or not species:
                        self._consume_ai_quota(user_id, "identity")
                        suggestion = infer_plant_identity(note=notes, filename="")
                        name = name or suggestion["name"]
                        species = species or suggestion["species"]
                        chinese_name = chinese_name or str(suggestion.get("chinese_name") or "")
                    else:
                        suggestion = self._identity_from_provided_values(
                            name=name,
                            species=species,
                            chinese_name=chinese_name,
                        )
                    location = str(payload.get("location") or "").strip() or "Home"
                    photo_url = None
                    initial_note = notes
                    file_payload = None
                    raw_diagnosis = payload.get("diagnosis_payload") or payload.get("diagnosis")
                    raw_tip = payload.get("tip_payload") or payload.get("tip")
                    raw_upload_token = payload.get("upload_token") or ""
                    client_created_at = payload.get("client_created_at")
                else:
                    fields, files = parse_multipart(self)
                    file_payload = pick_file(files)
                    thumbnail_payload = pick_file(files, field_names=("thumbnail",))
                    raw_upload_token = fields.get("upload_token") or ""
                    photo_url = store_upload(file_payload, prefix="plant") if file_payload else None
                    if not photo_url and raw_upload_token:
                        photo_url = photo_url_from_upload_token(str(raw_upload_token))
                    store_thumbnail(thumbnail_payload, photo_url=photo_url)
                    notes = str(fields.get("notes") or fields.get("note") or "").strip()
                    initial_note = notes
                    location = str(fields.get("location") or "").strip() or "Home"
                    name = str(fields.get("name") or "").strip()
                    species = str(fields.get("species") or "").strip()
                    chinese_name = str(fields.get("chinese_name") or "").strip()
                    if not name or not species:
                        self._consume_ai_quota(user_id, "identity")
                        suggestion = infer_plant_identity(
                            note=notes,
                            filename=str(file_payload.get("filename") or "") if file_payload else "",
                            content_type=str(file_payload.get("content_type") or "") if file_payload else "",
                            photo_bytes=bytes(file_payload.get("bytes") or b"") if file_payload else None,
                        )
                        name = name or suggestion["name"]
                        species = species or suggestion["species"]
                        chinese_name = chinese_name or str(suggestion.get("chinese_name") or "")
                    else:
                        suggestion = self._identity_from_provided_values(
                            name=name,
                            species=species,
                            chinese_name=chinese_name,
                        )
                    raw_diagnosis = fields.get("diagnosis_payload") or ""
                    raw_tip = fields.get("tip_payload") or ""
                    client_created_at = fields.get("client_created_at")

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

                provided_tip = None
                if isinstance(raw_tip, dict):
                    body = str(raw_tip.get("body") or "").strip()
                    if body:
                        provided_tip = {
                            "title": str(raw_tip.get("title") or "").strip() or "Care tip",
                            "body": body,
                            "source": str(raw_tip.get("source") or "").strip() or "reference",
                        }
                elif isinstance(raw_tip, str) and raw_tip.strip():
                    try:
                        parsed_tip = json.loads(raw_tip)
                    except json.JSONDecodeError:
                        parsed_tip = None
                    if isinstance(parsed_tip, dict):
                        body = str(parsed_tip.get("body") or "").strip()
                        if body:
                            provided_tip = {
                                "title": str(parsed_tip.get("title") or "").strip() or "Care tip",
                                "body": body,
                                "source": str(parsed_tip.get("source") or "").strip() or "reference",
                            }
                if not provided_tip:
                    provided_tip = default_tip_for_identity(name=name, species=species)
                if not chinese_name:
                    chinese_name = heuristic_chinese_name(name=name, species=species)

                with get_conn() as connection:
                    plant_id = make_plant_id(connection)
                    created_at = client_created_at_or_now(client_created_at)
                    create_plant(
                        connection,
                        plant_id=plant_id,
                        user_id=user_id,
                        name=name,
                        species=species,
                        chinese_name=chinese_name,
                        location=location,
                        notes="",
                        note_origin="empty",
                        tip_title=str((provided_tip or {}).get("title") or ""),
                        tip_body=str((provided_tip or {}).get("body") or ""),
                        tip_source=str((provided_tip or {}).get("source") or "empty"),
                        cover_photo_url=photo_url,
                        created_at=created_at,
                    )
                    created_checkin = None
                    if photo_url or initial_note:
                        plant_row = fetch_plant_row(connection, plant_id, user_id=user_id)
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
                    row = fetch_plant_row(connection, plant_id, user_id=user_id)
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
                    client_created_at = payload.get("client_created_at")
                else:
                    fields, files = parse_multipart(self)
                    note = str(fields.get("note") or "").strip()
                    client_created_at = fields.get("client_created_at")
                    file_payload = pick_file(files)
                    thumbnail_payload = pick_file(files, field_names=("thumbnail",))
                    photo_url = store_upload(file_payload, prefix=plant_id) if file_payload else None
                    store_thumbnail(thumbnail_payload, photo_url=photo_url)

                if not note and not photo_url:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Add a photo or a note for this check-in.")

                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    plant = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    consume_ai_quota(connection, user_id=str(user["id"]), action="checkin")
                    recent_checkins = [
                        serialize_checkin(checkin_row)
                        for checkin_row in list_checkin_rows(connection, plant_id)[:3]
                    ]
                    diagnosis = diagnose_plant(
                        plant=plant,
                        note=note,
                        has_photo=photo_url is not None,
                        recent_checkins=recent_checkins,
                        filename=str(file_payload.get("filename") or "") if file_payload else "",
                        content_type=str(file_payload.get("content_type") or "") if file_payload else "",
                        photo_bytes=bytes(file_payload.get("bytes") or b"") if file_payload else None,
                    )
                    checkin_id = f"{plant_id}-{uuid.uuid4().hex[:10]}"
                    created_at = client_created_at_or_now(client_created_at)
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
                    row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    latest = latest_checkin_row(connection, plant_id)
                    payload_out = {
                        "plant": serialize_plant_detail(connection, row),
                        "checkin": serialize_checkin(latest) if latest else None,
                    }
                    connection.commit()
                return self._send_json(payload_out, status=201)

            chat_message_match = re.fullmatch(r"/api/plants/([^/]+)/chat/messages", path)
            if chat_message_match:
                plant_id = chat_message_match.group(1)
                payload = parse_json_body(self)
                if not isinstance(payload, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Chat message payload must be a JSON object.")
                body = str(payload.get("body") or "").strip()
                checkin_id = str(payload.get("checkin_id") or "").strip() or None
                if not body:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Add a follow-up question first.")

                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    plant = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    consume_ai_quota(connection, user_id=str(user["id"]), action="chat")
                    thread = fetch_or_create_chat_thread(
                        connection,
                        plant_id=plant_id,
                        user_id=str(user["id"]),
                    )
                    recent_checkins = [
                        serialize_checkin(checkin_row)
                        for checkin_row in list_checkin_rows(connection, plant_id)[:3]
                    ]
                    recent_messages = [
                        serialize_chat_message(message_row)
                        for message_row in list_chat_message_rows(connection, str(thread["id"]), limit=6)
                    ]
                    focused_checkin = None
                    if checkin_id:
                        focused_row = fetch_checkin_row(connection, checkin_id, user_id=str(user["id"]))
                        if str(focused_row["plant_id"]) != plant_id:
                            raise ApiError(HTTPStatus.BAD_REQUEST, "That diagnosis belongs to a different plant.")
                        focused_checkin = serialize_checkin(focused_row)

                    answer_payload = answer_plant_followup(
                        plant=plant,
                        question=body,
                        recent_checkins=recent_checkins,
                        recent_messages=recent_messages,
                        rolling_summary=str(thread["rolling_summary"] or "").strip(),
                        focused_checkin=focused_checkin,
                    )
                    created_at = now_iso()
                    user_message_id = str(uuid.uuid4())
                    assistant_message_id = str(uuid.uuid4())
                    create_chat_message(
                        connection,
                        message_id=user_message_id,
                        thread_id=str(thread["id"]),
                        user_id=str(user["id"]),
                        plant_id=plant_id,
                        checkin_id=checkin_id,
                        role="user",
                        body=body,
                        suggested_actions=[],
                        watch_signals=[],
                        created_at=created_at,
                    )
                    create_chat_message(
                        connection,
                        message_id=assistant_message_id,
                        thread_id=str(thread["id"]),
                        user_id=str(user["id"]),
                        plant_id=plant_id,
                        checkin_id=checkin_id,
                        role="assistant",
                        body=str(answer_payload["answer"]),
                        suggested_actions=list(answer_payload.get("suggested_actions") or []),
                        watch_signals=list(answer_payload.get("watch_signals") or []),
                        created_at=created_at,
                    )
                    update_chat_thread_memory(
                        connection,
                        thread_id=str(thread["id"]),
                        rolling_summary=str(answer_payload.get("rolling_summary") or ""),
                        open_questions=list(answer_payload.get("open_questions") or []),
                        last_advice=list(answer_payload.get("last_advice") or []),
                        updated_at=created_at,
                    )
                    refreshed_thread = fetch_chat_thread_for_plant(
                        connection,
                        plant_id=plant_id,
                        user_id=str(user["id"]),
                    )
                    payload_out = {
                        "thread": serialize_chat_thread(refreshed_thread),
                        "user_message": serialize_chat_message(
                            connection.execute(
                                "SELECT * FROM chat_messages WHERE id = ?",
                                (user_message_id,),
                            ).fetchone()
                        ),
                        "assistant_message": serialize_chat_message(
                            connection.execute(
                                "SELECT * FROM chat_messages WHERE id = ?",
                                (assistant_message_id,),
                            ).fetchone()
                        ),
                        "focused_checkin": focused_checkin,
                    }
                    connection.commit()
                return self._send_json(payload_out, status=201)

            watering_toggle_match = re.fullmatch(r"/api/plants/([^/]+)/waterings/toggle", path)
            if watering_toggle_match:
                plant_id = watering_toggle_match.group(1)
                payload = parse_json_body(self)
                if not isinstance(payload, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Watering payload must be a JSON object.")
                watered_on = str(payload.get("watered_on") or "").strip() or today_date_iso()
                should_be_watered = bool(payload.get("watered", True))

                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", watered_on):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Watering date must use YYYY-MM-DD.")

                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    existing = fetch_watering_row(connection, plant_id=plant_id, watered_on=watered_on)
                    created = False
                    deleted = False
                    if should_be_watered and existing is None:
                        create_watering_event(
                            connection,
                            watering_id=str(uuid.uuid4()),
                            plant_id=plant_id,
                            watered_on=watered_on,
                            created_at=now_iso(),
                        )
                        created = True
                    elif not should_be_watered and existing is not None:
                        connection.execute("DELETE FROM waterings WHERE id = ?", (str(existing["id"]),))
                        deleted = True

                    if created or deleted:
                        connection.execute(
                            "UPDATE plants SET updated_at = ? WHERE id = ?",
                            (now_iso(), plant_id),
                        )

                    row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    payload_out = {
                        "created": created,
                        "deleted": deleted,
                        "watered": should_be_watered,
                        "watered_on": watered_on,
                        "plant": serialize_plant_detail(connection, row),
                    }
                    connection.commit()
                return self._send_json(payload_out, status=201 if created else 200)

            watering_match = re.fullmatch(r"/api/plants/([^/]+)/waterings", path)
            if watering_match:
                plant_id = watering_match.group(1)
                payload = parse_json_body(self)
                if payload is None:
                    payload = {}
                if not isinstance(payload, dict):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Watering payload must be a JSON object.")
                watered_on = str(payload.get("watered_on") or "").strip() or today_date_iso()

                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", watered_on):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Watering date must use YYYY-MM-DD.")

                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    existing = fetch_watering_row(connection, plant_id=plant_id, watered_on=watered_on)
                    created = False
                    if existing is None:
                        create_watering_event(
                            connection,
                            watering_id=str(uuid.uuid4()),
                            plant_id=plant_id,
                            watered_on=watered_on,
                            created_at=now_iso(),
                        )
                        created = True
                    row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    payload_out = {
                        "created": created,
                        "watered_on": watered_on,
                        "plant": serialize_plant_detail(connection, row),
                    }
                    connection.commit()
                return self._send_json(payload_out, status=201 if created else 200)

            raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")
        except ApiError as exc:
            self._send_api_error(exc)

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            checkin_match = re.fullmatch(r"/api/checkins/([^/]+)", path)
            if checkin_match:
                checkin_id = checkin_match.group(1)
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    checkin_row = fetch_checkin_row(connection, checkin_id, user_id=str(user["id"]))
                    plant_id = str(checkin_row["plant_id"])
                    plant_row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    photo_url = checkin_row["photo_url"]

                    connection.execute("DELETE FROM checkins WHERE id = ?", (checkin_id,))
                    connection.execute(
                        "UPDATE chat_messages SET checkin_id = NULL WHERE checkin_id = ?",
                        (checkin_id,),
                    )
                    connection.execute(
                        "UPDATE plants SET updated_at = ? WHERE id = ?",
                        (now_iso(), plant_id),
                    )
                    remaining_checkins = list_checkin_rows(connection, plant_id)
                    connection.commit()

                if photo_url and photo_url != plant_row["cover_photo_url"]:
                    if not any(row["photo_url"] == photo_url for row in remaining_checkins):
                        maybe_delete_upload(photo_url)

                return self._send_json(
                    {"deleted": True, "checkin_id": checkin_id, "plant_id": plant_id}
                )

            watering_match = re.fullmatch(r"/api/plants/([^/]+)/waterings", path)
            if watering_match:
                plant_id = watering_match.group(1)
                watered_on = parse_qs(parsed.query).get("date", [today_date_iso()])[0]
                watered_on = str(watered_on or "").strip() or today_date_iso()
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", watered_on):
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Watering date must use YYYY-MM-DD.")

                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    existing = fetch_watering_row(connection, plant_id=plant_id, watered_on=watered_on)
                    deleted = False
                    if existing is not None:
                        connection.execute("DELETE FROM waterings WHERE id = ?", (str(existing["id"]),))
                        connection.execute(
                            "UPDATE plants SET updated_at = ? WHERE id = ?",
                            (now_iso(), plant_id),
                        )
                        deleted = True
                    row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    payload_out = {
                        "deleted": deleted,
                        "watered_on": watered_on,
                        "plant": serialize_plant_detail(connection, row),
                    }
                    connection.commit()
                return self._send_json(payload_out)

            plant_match = re.fullmatch(r"/api/plants/([^/]+)", path)
            if not plant_match:
                raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")

            payload = parse_json_body(self)
            if not isinstance(payload, dict):
                raise ApiError(HTTPStatus.BAD_REQUEST, "Update payload must be a JSON object.")

            plant_id = plant_match.group(1)
            with get_conn() as connection:
                user = self._resolve_current_user(connection)
                fetch_plant_row(connection, plant_id, user_id=str(user["id"]))

                updates: list[str] = []
                params: list[object] = []

                if "name" in payload:
                    name = str(payload.get("name") or "").strip()
                    if not name:
                        raise ApiError(HTTPStatus.BAD_REQUEST, "Plant name cannot be empty.")
                    updates.append("name = ?")
                    params.append(name)

                if "notes" in payload:
                    raise ApiError(
                        HTTPStatus.BAD_REQUEST,
                        "Plant-level notes were replaced by check-in notes.",
                    )

                if not updates:
                    raise ApiError(HTTPStatus.BAD_REQUEST, "Nothing to update.")

                updated_at = now_iso()
                updates.append("updated_at = ?")
                params.append(updated_at)
                params.append(plant_id)

                connection.execute(
                    f"UPDATE plants SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                payload_out = {"plant": serialize_plant_detail(connection, row)}
                connection.commit()
            return self._send_json(payload_out)
        except ApiError as exc:
            self._send_api_error(exc)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            checkin_match = re.fullmatch(r"/api/checkins/([^/]+)", path)
            if checkin_match:
                checkin_id = checkin_match.group(1)
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    checkin_row = fetch_checkin_row(connection, checkin_id, user_id=str(user["id"]))
                    plant_id = str(checkin_row["plant_id"])
                    plant_row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                    photo_url = checkin_row["photo_url"]

                    connection.execute("DELETE FROM checkins WHERE id = ?", (checkin_id,))
                    connection.execute(
                        "UPDATE chat_messages SET checkin_id = NULL WHERE checkin_id = ?",
                        (checkin_id,),
                    )
                    connection.execute(
                        "UPDATE plants SET updated_at = ? WHERE id = ?",
                        (now_iso(), plant_id),
                    )
                    remaining_checkins = list_checkin_rows(connection, plant_id)
                    connection.commit()

                if photo_url and photo_url != plant_row["cover_photo_url"]:
                    if not any(row["photo_url"] == photo_url for row in remaining_checkins):
                        maybe_delete_upload(photo_url)

                return self._send_json(
                    {"deleted": True, "checkin_id": checkin_id, "plant_id": plant_id}
                )

            plant_match = re.fullmatch(r"/api/plants/([^/]+)", path)
            if not plant_match:
                raise ApiError(HTTPStatus.NOT_FOUND, "Not found.")

            plant_id = plant_match.group(1)
            with get_conn() as connection:
                user = self._resolve_current_user(connection)
                row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
                checkin_rows = list_checkin_rows(connection, plant_id)
                upload_urls = [row["cover_photo_url"]]
                upload_urls.extend(checkin_row["photo_url"] for checkin_row in checkin_rows)

                connection.execute("DELETE FROM waterings WHERE plant_id = ?", (plant_id,))
                connection.execute("DELETE FROM chat_messages WHERE plant_id = ?", (plant_id,))
                connection.execute("DELETE FROM chat_threads WHERE plant_id = ?", (plant_id,))
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
    print(model_runtime_summary())
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()
