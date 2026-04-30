from __future__ import annotations

import json
import re
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

from .config import STATIC_DIR, UPLOAD_DIR
from .data import (
    create_or_claim_user,
    create_checkin,
    create_plant,
    ensure_demo_seeded,
    fetch_checkin_row,
    fetch_plant_row,
    fetch_user_by_id,
    get_conn,
    has_claimable_user,
    init_db,
    latest_checkin_row,
    list_checkin_rows,
    list_plant_rows_for_user,
    make_plant_id,
    migrate_plant_ids_to_uuid,
    normalize_legacy_checkins,
    now_iso,
    serialize_checkin,
    serialize_plant_detail,
    serialize_plant_summary,
    serialize_user,
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
    store_upload,
    upload_token_from_url,
)
from .plant_ai import (
    build_add_preview,
    default_tip_for_identity,
    diagnose_plant,
    heuristic_diagnosis,
    heuristic_chinese_name,
    infer_plant_identity,
    normalize_diagnosis_payload,
)


class MyGardenHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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

    def _current_user_id(self) -> str:
        return str(self.headers.get("X-My-Garden-User-Id") or "").strip()

    def _resolve_current_user(self, connection, *, required: bool = True):
        user_id = self._current_user_id()
        if not user_id:
            if required:
                raise ApiError(401, "Choose your garden profile first.")
            return None
        try:
            return fetch_user_by_id(connection, user_id)
        except ApiError:
            if required:
                raise
            return None

    def _session_payload(self, connection, user_row=None, *, claimed_legacy_garden: bool = False):
        return {
            "user": serialize_user(user_row) if user_row is not None else None,
            "claimable_legacy_garden": has_claimable_user(connection),
            "claimed_legacy_garden": claimed_legacy_garden,
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

            if path == "/api/plants":
                with get_conn() as connection:
                    user = self._resolve_current_user(connection)
                    rows = list_plant_rows_for_user(connection, str(user["id"]))
                    payload = {"plants": [serialize_plant_summary(connection, row) for row in rows]}
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
                with get_conn() as connection:
                    user, claimed_legacy_garden = create_or_claim_user(
                        connection,
                        name=name,
                        email=email,
                    )
                    payload_out = self._session_payload(
                        connection,
                        user,
                        claimed_legacy_garden=claimed_legacy_garden,
                    )
                    connection.commit()
                return self._send_json(payload_out, status=201)

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
                    chinese_name = str(payload.get("chinese_name") or "").strip() or str(suggestion.get("chinese_name") or "")
                    location = str(payload.get("location") or "").strip() or "Home"
                    photo_url = None
                    initial_note = notes
                    file_payload = None
                    raw_diagnosis = payload.get("diagnosis_payload") or payload.get("diagnosis")
                    raw_tip = payload.get("tip_payload") or payload.get("tip")
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
                    chinese_name = str(fields.get("chinese_name") or "").strip() or str(suggestion.get("chinese_name") or "")
                    raw_diagnosis = fields.get("diagnosis_payload") or ""
                    raw_tip = fields.get("tip_payload") or ""

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
                    user = self._resolve_current_user(connection)
                    plant_id = make_plant_id(connection)
                    created_at = now_iso()
                    create_plant(
                        connection,
                        plant_id=plant_id,
                        user_id=str(user["id"]),
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
                        plant_row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
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
                    row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
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
                    user = self._resolve_current_user(connection)
                    plant = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
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
                    row = fetch_plant_row(connection, plant_id, user_id=str(user["id"]))
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
