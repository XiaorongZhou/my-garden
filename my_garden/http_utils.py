from __future__ import annotations

import json
import mimetypes
import uuid
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from .config import STATIC_DIR, UPLOAD_DIR
from .errors import ApiError


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


def safe_child(root: Path, raw_relative_path: str) -> Path:
    candidate = (root / raw_relative_path).resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise ApiError(HTTPStatus.BAD_REQUEST, "Invalid path.")
    return candidate


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


def content_type_for(path: Path) -> str:
    if path.suffix == ".webmanifest":
        return "application/manifest+json"
    if path.suffix == ".svg":
        return "image/svg+xml"
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed or "application/octet-stream"


def static_index_path() -> Path:
    return STATIC_DIR / "index.html"
