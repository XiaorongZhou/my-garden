from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
import tempfile
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from .config import (
    HEIC_MIME_TYPES,
    HEIC_SUFFIXES,
    OPENAI_PLANT_MODEL,
    OPENAI_RESPONSES_URL,
    OPENAI_TIMEOUT_SECONDS,
    SUPPORTED_VISION_MIME_TYPES,
    SUPPORTED_VISION_SUFFIXES,
)


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


PLANT_IDENTITY_CANDIDATES = [
    {
        "tokens": ("maidenhair", "adiantum"),
        "name": "Maidenhair Fern",
        "species": "Adiantum raddianum",
        "chinese_name": "铁线蕨",
    },
    {
        "tokens": ("cat palm", "chamaedorea"),
        "name": "Cat Palm",
        "species": "Chamaedorea cataractarum",
        "chinese_name": "猫棕",
    },
    {
        "tokens": ("snake plant", "sansevieria", "dracaena trifasciata"),
        "name": "Snake Plant",
        "species": "Dracaena trifasciata",
        "chinese_name": "虎尾兰",
    },
    {
        "tokens": ("pothos", "epipremnum"),
        "name": "Pothos",
        "species": "Epipremnum aureum",
        "chinese_name": "绿萝",
    },
    {
        "tokens": ("monstera",),
        "name": "Monstera",
        "species": "Monstera deliciosa",
        "chinese_name": "龟背竹",
    },
    {
        "tokens": ("philodendron",),
        "name": "Philodendron",
        "species": "Philodendron hederaceum",
        "chinese_name": "喜林芋",
    },
    {
        "tokens": ("fiddle", "ficus lyrata"),
        "name": "Fiddle Leaf Fig",
        "species": "Ficus lyrata",
        "chinese_name": "琴叶榕",
    },
    {
        "tokens": ("rubber plant", "ficus elastica"),
        "name": "Rubber Plant",
        "species": "Ficus elastica",
        "chinese_name": "橡皮树",
    },
    {
        "tokens": ("zz plant", "zamioculcas"),
        "name": "ZZ Plant",
        "species": "Zamioculcas zamiifolia",
        "chinese_name": "雪铁芋",
    },
    {
        "tokens": ("spider plant", "chlorophytum"),
        "name": "Spider Plant",
        "species": "Chlorophytum comosum",
        "chinese_name": "吊兰",
    },
    {
        "tokens": ("peace lily", "spathiphyllum"),
        "name": "Peace Lily",
        "species": "Spathiphyllum",
        "chinese_name": "白掌",
    },
    {
        "tokens": ("fern",),
        "name": "Fern",
        "species": "Unknown fern",
        "chinese_name": "蕨类植物",
    },
    {
        "tokens": ("palm",),
        "name": "Palm",
        "species": "Unknown palm",
        "chinese_name": "棕榈",
    },
    {
        "tokens": ("succulent", "cactus"),
        "name": "Succulent",
        "species": "Unknown succulent",
        "chinese_name": "多肉植物",
    },
]


def heuristic_chinese_name(*, name: str = "", species: str = "") -> str:
    text = f"{name} {species}".lower()
    for candidate in PLANT_IDENTITY_CANDIDATES:
        if any(token in text for token in candidate["tokens"]):
            return str(candidate["chinese_name"])
    return ""


def default_tip_for_identity(*, name: str = "", species: str = "") -> dict[str, str] | None:
    text = f"{name} {species}".lower()
    if any(token in text for token in ("maidenhair", "adiantum", "fern")):
        return {
            "title": "Care tip",
            "body": "Gets crispy quickly when the air feels dry.",
            "source": "reference",
        }
    if any(token in text for token in ("cat palm", "chamaedorea", "palm")):
        return {
            "title": "Care tip",
            "body": "Likes even moisture and brighter mornings.",
            "source": "reference",
        }
    if any(token in text for token in ("spider plant", "chlorophytum")):
        return {
            "title": "Care tip",
            "body": "Leaf tips can brown when the mix stays salty or the air gets too dry.",
            "source": "heuristic",
        }
    if any(token in text for token in ("snake plant", "sansevieria", "dracaena trifasciata")):
        return {
            "title": "Care tip",
            "body": "This one usually does better drying out between waterings than staying evenly moist.",
            "source": "heuristic",
        }
    if any(token in text for token in ("succulent", "graptopetalum", "graptoveria", "cactus")):
        return {
            "title": "Care tip",
            "body": "Let the potting mix dry well before watering again, especially after lower-light days.",
            "source": "heuristic",
        }
    return None


def heuristic_plant_identity(*, note: str = "", filename: str = "") -> dict[str, str]:
    text = f"{filename} {note}".lower()
    for candidate in PLANT_IDENTITY_CANDIDATES:
        if any(token in text for token in candidate["tokens"]):
            return {
                "name": str(candidate["name"]),
                "species": str(candidate["species"]),
                "chinese_name": str(candidate["chinese_name"]),
                "confidence": "medium",
                "source": "heuristic",
                "caption": "Using a local backup guess from the filename and any notes you added.",
            }
    return {
        "name": "Unknown Houseplant",
        "species": "Unknown houseplant",
        "chinese_name": "",
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
        "required": ["common_name", "species", "chinese_name", "confidence", "caption"],
        "properties": {
            "common_name": {"type": "string"},
            "species": {"type": "string"},
            "chinese_name": {"type": "string"},
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
                        "a common Simplified Chinese plant name if there is one, a confidence value, "
                        "and a short caption the app can show to the user."
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
        "chinese_name": str(parsed.get("chinese_name") or "").strip() or heuristic_chinese_name(name=name, species=species),
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
            "chinese_name",
            "confidence",
            "caption",
            "health_status",
            "diagnosis_title",
            "diagnosis_summary",
            "care_steps",
            "tip_title",
            "tip_body",
        ],
        "properties": {
            "common_name": {"type": "string"},
            "species": {"type": "string"},
            "chinese_name": {"type": "string"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "caption": {"type": "string"},
            "health_status": {"type": "string", "enum": ["thriving", "watch", "needs_care"]},
            "diagnosis_title": {"type": "string"},
            "diagnosis_summary": {"type": "string"},
            "tip_title": {"type": "string"},
            "tip_body": {"type": "string"},
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
                        "- chinese_name: a common Simplified Chinese plant name if there is one, otherwise an empty string\n"
                        "- confidence: high, medium, or low\n"
                        "- caption: one short line the app can show\n"
                        "- health_status: thriving, watch, or needs_care\n"
                        "- diagnosis_title: a short title for the first read\n"
                        "- diagnosis_summary: a concise 1-2 sentence initial diagnosis\n"
                        "- tip_title: a short evergreen plant-tip title, or an empty string if unnecessary\n"
                        "- tip_body: one short evergreen care tip about this plant's tendency, not today's diagnosis\n"
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
        "chinese_name": str(parsed.get("chinese_name") or "").strip(),
        "confidence": str(parsed.get("confidence") or "low").strip().lower(),
        "source": "openai",
        "caption": str(parsed.get("caption") or "").strip() or "Identified from the photo you added.",
    }
    if suggestion["confidence"] not in {"high", "medium", "low"}:
        suggestion["confidence"] = "low"
    if not suggestion["chinese_name"]:
        suggestion["chinese_name"] = heuristic_chinese_name(
            name=suggestion["name"],
            species=suggestion["species"],
        )
    diagnosis = normalize_diagnosis_payload(parsed)
    tip_body = str(parsed.get("tip_body") or "").strip()
    tip = None
    if tip_body:
        tip = {
            "title": str(parsed.get("tip_title") or "").strip() or "Care tip",
            "body": tip_body,
            "source": "model",
        }
    return {
        "suggestion": suggestion,
        "diagnosis": diagnosis,
        "tip": tip,
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
    preview = {
        "suggestion": suggestion,
        "diagnosis": diagnosis,
        "tip": default_tip_for_identity(name=suggestion["name"], species=suggestion["species"]),
    }

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


def heuristic_diagnosis(plant, note: str, has_photo: bool) -> dict[str, object]:
    profile = species_profile(str(plant["species"]))
    combined = note.lower()

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
    plant,
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
    saved_tip = str(plant["tip_body"] or "").strip() or "No saved plant tip."
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
                        f"General plant tip: {saved_tip}\n"
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
    plant,
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
