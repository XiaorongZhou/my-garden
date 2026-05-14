from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

from .ai_providers import (
    ModelImage,
    active_provider_source,
    call_structured_output,
    live_model_available,
    log_model_event,
)
from .config import (
    HEIC_MIME_TYPES,
    HEIC_SUFFIXES,
    SUPPORTED_VISION_MIME_TYPES,
    SUPPORTED_VISION_SUFFIXES,
)

CHAT_IMPORT_MARKERS = (
    "---",
    "##",
    "###",
    "👉",
    "✅",
    "🌿",
    "🧠",
    "⚠️",
    "❌",
    "🪴",
    "🫚",
    "🥇",
    "🥈",
    "🥉",
    "一\u53e5\u8bdd\u603b\u7ed3",
)

GENERIC_CHAT_TITLES = {
    "可以的",
    "好问题",
    "太好了",
    "哈哈",
    "这个要直接跟你说实话",
    "很好你注意到了这个细节",
    "你这张近景很关键",
    "你这个状态我一看就知道发生了什么",
}

GENERIC_CHAT_OPENERS = (
    "可以的",
    "好问题",
    "太好了",
    "哈哈",
    "这个要直接跟你说实话",
    "很好你注意到了这个细节",
    "你这张近景很关键",
    "你这个状态我一看就知道发生了什么",
    "我帮你认真看了一下",
    "我帮你具体看了一下",
    "我帮你快速判断",
    "先别慌",
)

HEADING_LIKE_CHUNKS = (
    "结论先说",
    "一句话总结",
    "现在发生了什么",
    "为什么",
    "怎么移栽",
    "什么时候可以",
    "一个关键判断",
    "正确补救方法",
    "之后会发生什么",
    "以后避免的方法",
    "你这个厕所评估",
    "放厕所/淋浴间",
    "对照你的这颗来理解",
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


def live_model_unavailable_caption() -> str:
    if active_provider_source() == "local":
        return "Using the local backup guess for now. Start the local plant model server to enable photo-based plant ID."
    return "Using the local backup guess for now. Add an OpenAI API key to enable photo-based plant ID."


def live_model_failure_caption() -> str:
    if active_provider_source() == "local":
        return "The local plant model was unavailable, so we fell back to the local guess."
    return "The live plant ID model was unavailable, so we fell back to the local guess."


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
    parsed = call_structured_output(
        schema_name="plant_identity",
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=(
            "Identify this plant for a personal plant log.\n"
            f"Owner note: {note_text}\n"
            f"Filename: {filename_text}\n"
            "Return a human-friendly common name, a likely Latin species if you can support it, "
            "a common Simplified Chinese plant name if there is one, a confidence value, "
            "and a short caption the app can show to the user."
        ),
        image=ModelImage(
            filename=filename,
            content_type=content_type,
            photo_bytes=photo_bytes,
        ),
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
        "source": active_provider_source(),
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


def strip_chat_formatting(text: str) -> str:
    cleaned = str(text or "")
    cleaned = cleaned.replace("\ufeff", "")
    cleaned = cleaned.replace("**", "")
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.M)
    cleaned = re.sub(r"^[\-\*\u2022]+\s*", "", cleaned, flags=re.M)
    cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned, flags=re.M)
    cleaned = re.sub(r"[\U0001F300-\U0001FAFF]", "", cleaned)
    cleaned = re.sub(r"[👉✅⚠️❌🌿🧠💧☀️🌡️🪴🫚🥇🥈🥉]", "", cleaned)
    cleaned = re.sub(r"\n-{3,}\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def split_human_sentences(text: str) -> list[str]:
    chunks = re.split(r"(?:\n+|(?<=[。！？!?])\s+|(?<=\.)\s+(?=[A-Z]))", strip_chat_formatting(text))
    return [chunk.strip(" -") for chunk in chunks if chunk and chunk.strip(" -")]


def looks_like_verbose_chat_import(title: str, summary: str) -> bool:
    normalized_title = strip_chat_formatting(title)
    normalized_summary = str(summary or "")
    if any(marker in summary or marker in title for marker in CHAT_IMPORT_MARKERS):
        return True
    if len(normalized_summary) > 320:
        return True
    if len(normalized_title) > 72:
        return True
    if normalized_title in GENERIC_CHAT_TITLES:
        return True
    return False


def heuristic_compact_imported_diagnosis(
    *,
    diagnosis_title: str,
    diagnosis_summary: str,
    care_steps: list[str] | None = None,
    health_status: str = "watch",
) -> dict[str, object]:
    clean_title = strip_chat_formatting(diagnosis_title)
    sentences = split_human_sentences(diagnosis_summary)
    informative_sentences = [
        sentence
        for sentence in sentences
        if sentence
        and len(sentence) >= 6
        and not any(sentence.startswith(prefix) for prefix in GENERIC_CHAT_OPENERS)
        and not any(marker in sentence for marker in HEADING_LIKE_CHUNKS)
        and not sentence.endswith("：")
    ]
    chosen_sentences = (informative_sentences or sentences)[:3]
    compact_summary = " ".join(chosen_sentences).strip()
    compact_summary = re.sub(r"\s+", " ", compact_summary)
    compact_summary = compact_summary[:360].rstrip(" ,;:-")

    if (
        not clean_title
        or clean_title in GENERIC_CHAT_TITLES
        or any(clean_title.startswith(prefix) for prefix in GENERIC_CHAT_OPENERS)
        or len(clean_title) > 42
    ):
        if chosen_sentences:
            clean_title = chosen_sentences[0]
        elif compact_summary:
            clean_title = compact_summary
        else:
            clean_title = "Imported diagnosis"

    clean_title = re.sub(r"\s+", " ", clean_title).strip(" ,;:-")
    clean_title = re.sub(r"[。！？!?].*$", "", clean_title).strip(" ,;:-")
    if len(clean_title) > 60:
        clean_title = clean_title[:60].rstrip(" ,;:-")

    cleaned_steps = [strip_chat_formatting(step) for step in (care_steps or []) if strip_chat_formatting(step)]
    if not cleaned_steps and sentences:
        cleaned_steps = [sentence for sentence in sentences if sentence.startswith(("保持", "避免", "检查", "浸盆", "换土", "Water", "Check", "Keep", "Move"))][:3]

    return {
        "health_status": health_status,
        "diagnosis_title": clean_title or "Imported diagnosis",
        "diagnosis_summary": compact_summary or strip_chat_formatting(diagnosis_summary)[:240],
        "care_steps": cleaned_steps[:3],
    }


def compact_imported_diagnosis(
    *,
    plant_name: str,
    species: str,
    chinese_name: str,
    owner_note: str,
    diagnosis_title: str,
    diagnosis_summary: str,
    care_steps: list[str] | None = None,
    health_status: str = "watch",
) -> dict[str, object]:
    fallback = heuristic_compact_imported_diagnosis(
        diagnosis_title=diagnosis_title,
        diagnosis_summary=diagnosis_summary,
        care_steps=care_steps,
        health_status=health_status,
    )
    if not live_model_available():
        log_model_event("fallback", flow="compact_import", reason="live_model_unavailable")
        return fallback

    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["diagnosis_title", "diagnosis_summary", "care_steps"],
        "properties": {
            "diagnosis_title": {"type": "string"},
            "diagnosis_summary": {"type": "string"},
            "care_steps": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
        },
    }
    source_text = f"{diagnosis_title}\n\n{diagnosis_summary}".strip()
    system_prompt = (
        "You rewrite historical plant diagnoses from long chat transcripts into concise mobile-app copy. "
        "Keep the same language as the source diagnosis. If the source includes Chinese, prefer Simplified Chinese. "
        "Remove emojis, markdown, headings, filler, repetition, and chatty framing. "
        "Do not add new facts or change the meaning. "
        "Return plain, compact text only as strict JSON."
    )
    try:
        parsed = call_structured_output(
            schema_name="compact_imported_diagnosis",
            schema=schema,
            system_prompt=system_prompt,
            user_prompt=(
                "Rewrite this historical plant diagnosis for a timeline card.\n"
                f"Plant name: {plant_name}\n"
                f"Chinese name: {chinese_name or 'None'}\n"
                f"Species: {species}\n"
                f"Owner note: {owner_note or 'None'}\n"
                f"Current health status: {health_status}\n"
                f"Original diagnosis:\n{source_text}\n\n"
                f"Existing care steps: {json.dumps(care_steps or [], ensure_ascii=False)}\n\n"
                "Requirements:\n"
                "- diagnosis_title: very short and scannable, with no emoji or markdown\n"
                "- diagnosis_summary: 1-3 short sentences, readable in a mobile app\n"
                "- care_steps: 0-3 short concrete steps\n"
                "- keep the same advice and uncertainty level\n"
                "- do not mention ChatGPT, import, or formatting cleanup"
            ),
        )
    except RuntimeError as exc:
        log_model_event("fallback", flow="compact_import", reason=str(exc)[:220])
        return fallback

    compacted = {
        "health_status": health_status,
        "diagnosis_title": strip_chat_formatting(str(parsed.get("diagnosis_title") or "")).strip(),
        "diagnosis_summary": strip_chat_formatting(str(parsed.get("diagnosis_summary") or "")).strip(),
        "care_steps": [strip_chat_formatting(step) for step in parsed.get("care_steps") or [] if strip_chat_formatting(step)][:3],
    }
    if not compacted["diagnosis_title"] or not compacted["diagnosis_summary"]:
        return fallback
    return compacted


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
    parsed = call_structured_output(
        schema_name="plant_intake_preview",
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=(
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
        image=ModelImage(
            filename=filename,
            content_type=content_type,
            photo_bytes=photo_bytes,
        ),
    )
    suggestion = {
        "name": str(parsed.get("common_name") or "").strip() or "Unknown Houseplant",
        "species": str(parsed.get("species") or "").strip() or "Unknown houseplant",
        "chinese_name": str(parsed.get("chinese_name") or "").strip(),
        "confidence": str(parsed.get("confidence") or "low").strip().lower(),
        "source": active_provider_source(),
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
    except RuntimeError as exc:
        log_model_event("fallback", flow="plant_intake", reason=f"image_prepare_failed: {exc}")
        suggestion["caption"] = "This photo format could not be prepared for live plant ID, so we used a local backup guess."
        return preview
    if not supports_vision_input(filename=model_filename, content_type=model_content_type):
        log_model_event("fallback", flow="plant_intake", reason="unsupported_vision_input")
        suggestion["caption"] = "This photo format is not supported by the live vision model yet, so we used a local backup guess."
        return preview
    if not live_model_available():
        log_model_event("fallback", flow="plant_intake", reason="live_model_unavailable")
        suggestion["caption"] = live_model_unavailable_caption()
        return preview
    try:
        return preview_new_plant_with_model(
            note=note,
            filename=model_filename,
            content_type=model_content_type,
            photo_bytes=model_bytes,
        )
    except RuntimeError as exc:
        log_model_event("fallback", flow="plant_intake", reason=str(exc)[:220])
        suggestion["caption"] = live_model_failure_caption()
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
    except RuntimeError as exc:
        log_model_event("fallback", flow="plant_identity", reason=f"image_prepare_failed: {exc}")
        fallback["caption"] = "This photo format could not be prepared for live plant ID, so we used a local backup guess."
        return fallback
    if not supports_vision_input(filename=model_filename, content_type=model_content_type):
        log_model_event("fallback", flow="plant_identity", reason="unsupported_vision_input")
        fallback["caption"] = (
            "This photo format is not supported by the live vision model yet, so we used a local backup guess."
        )
        return fallback
    if not live_model_available():
        log_model_event("fallback", flow="plant_identity", reason="live_model_unavailable")
        fallback["caption"] = live_model_unavailable_caption()
        return fallback
    try:
        return identify_plant_with_model(
            note=note,
            filename=model_filename,
            content_type=model_content_type,
            photo_bytes=model_bytes,
        )
    except RuntimeError as exc:
        log_model_event("fallback", flow="plant_identity", reason=str(exc)[:220])
        fallback["caption"] = live_model_failure_caption()
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


def recent_checkin_context(recent_checkins: list[dict[str, object]] | None) -> str:
    if not recent_checkins:
        return "No previous check-ins."

    context_lines: list[str] = []
    for index, checkin in enumerate(recent_checkins[:3], start=1):
        created_at = str(checkin.get("created_at") or "").strip() or "Unknown time"
        status = str(checkin.get("health_status") or "watch").strip() or "watch"
        title = str(checkin.get("diagnosis_title") or "").strip() or "No diagnosis title"
        summary = str(checkin.get("diagnosis_summary") or "").strip() or "No saved summary."
        note = str(checkin.get("note") or "").strip() or "No owner note."
        care_steps = checkin.get("care_steps") or []
        if isinstance(care_steps, list) and care_steps:
            rendered_steps = "; ".join(str(step).strip() for step in care_steps if str(step).strip())
        else:
            rendered_steps = "No saved next steps."
        context_lines.append(
            f"{index}. {created_at}\n"
            f"Status: {status}\n"
            f"Diagnosis title: {title}\n"
            f"Diagnosis summary: {summary}\n"
            f"Owner note: {note}\n"
            f"Previous suggested next steps: {rendered_steps}"
        )
    return "\n\n".join(context_lines)


def diagnose_plant_with_model(
    *,
    plant,
    note: str,
    recent_checkins: list[dict[str, object]] | None = None,
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
    recent_history = recent_checkin_context(recent_checkins)
    parsed = call_structured_output(
        schema_name="plant_diagnosis",
        schema=schema,
        system_prompt=system_prompt,
        user_prompt=(
            "Diagnose this existing plant check-in.\n"
            f"Plant name: {plant['name']}\n"
            f"Known species: {plant['species']}\n"
            f"Location: {plant['location'] or 'Home'}\n"
            f"General plant tip: {saved_tip}\n"
            f"Recent check-in history (newest first, context only):\n{recent_history}\n"
            f"Today's owner note: {note_text}\n"
            "Return JSON only.\n"
            "Use the known plant identity as fixed context.\n"
            "Use the recent check-in history for continuity, but prioritize today's photo and note if they clearly differ.\n"
            "Do not identify the plant again.\n"
            "Do not suggest a new species.\n"
            "Provide:\n"
            "- health_status: thriving, watch, or needs_care\n"
            "- diagnosis_title: a short title\n"
            "- diagnosis_summary: a concise 1-2 sentence diagnosis\n"
            "- care_steps: 0-3 concrete next actions for the next few days"
        ),
        image=(
            ModelImage(
                filename=filename,
                content_type=content_type,
                photo_bytes=photo_bytes,
            )
            if photo_bytes
            else None
        ),
    )
    return normalize_diagnosis_payload(parsed)


def diagnose_plant(
    *,
    plant,
    note: str,
    has_photo: bool,
    recent_checkins: list[dict[str, object]] | None = None,
    filename: str = "",
    content_type: str = "",
    photo_bytes: bytes | None = None,
) -> dict[str, object]:
    if live_model_available() and (note.strip() or photo_bytes):
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
                recent_checkins=recent_checkins,
                filename=model_filename,
                content_type=model_content_type,
                photo_bytes=model_bytes,
            )
        except RuntimeError as exc:
            log_model_event("fallback", flow="plant_diagnosis", reason=str(exc)[:220])
            pass

    if not live_model_available():
        log_model_event("fallback", flow="plant_diagnosis", reason="live_model_unavailable")
    return heuristic_diagnosis(plant, note, has_photo)


def _truncate_text(value: str, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _clean_string_list(values: object, *, limit: int = 3, item_limit: int = 120) -> list[str]:
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    for value in values:
        text = _truncate_text(str(value or "").strip(), item_limit)
        if not text:
            continue
        cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def recent_chat_context(recent_messages: list[dict[str, object]] | None) -> str:
    if not recent_messages:
        return "No previous chat messages."

    rendered: list[str] = []
    for message in recent_messages[-6:]:
        role = str(message.get("role") or "").strip().lower() or "assistant"
        label = "User" if role == "user" else "Assistant"
        body = _truncate_text(str(message.get("body") or "").strip() or "No message body.", 260)
        rendered.append(f"{label}: {body}")
    return "\n".join(rendered)


def focused_checkin_context(focused_checkin: dict[str, object] | None) -> str:
    if not focused_checkin:
        return "No focused diagnosis anchor."
    created_at = str(focused_checkin.get("created_at") or "").strip() or "Unknown time"
    title = str(focused_checkin.get("diagnosis_title") or "").strip() or "No diagnosis title"
    summary = str(focused_checkin.get("diagnosis_summary") or "").strip() or "No diagnosis summary."
    note = str(focused_checkin.get("note") or "").strip() or "No owner note."
    care_steps = focused_checkin.get("care_steps") or []
    rendered_steps = "; ".join(_clean_string_list(care_steps, limit=3, item_limit=100)) or "No saved next steps."
    return (
        f"Focused diagnosis timestamp: {created_at}\n"
        f"Focused diagnosis title: {title}\n"
        f"Focused diagnosis summary: {summary}\n"
        f"Focused owner note: {note}\n"
        f"Focused next steps: {rendered_steps}"
    )


def build_plant_chat_context(
    *,
    plant,
    recent_checkins: list[dict[str, object]] | None,
    recent_messages: list[dict[str, object]] | None,
    rolling_summary: str = "",
    focused_checkin: dict[str, object] | None = None,
) -> str:
    plant_tip = str(plant["tip_body"] or "").strip()
    return (
        f"Plant name: {plant['name']}\n"
        f"Chinese name: {str(plant['chinese_name'] or '').strip() or 'None'}\n"
        f"Known species: {plant['species']}\n"
        f"Location: {plant['location'] or 'Home'}\n"
        f"Stable plant tendency: {plant_tip or 'None saved.'}\n\n"
        f"Rolling plant chat summary:\n{rolling_summary.strip() or 'No prior chat summary.'}\n\n"
        f"Recent check-in history (newest first):\n{recent_checkin_context(recent_checkins)}\n\n"
        f"Recent plant chat turns:\n{recent_chat_context(recent_messages)}\n\n"
        f"Focused diagnosis context:\n{focused_checkin_context(focused_checkin)}"
    )


def followup_prompt_suggestions(*, plant, latest_checkin: dict[str, object] | None = None) -> list[str]:
    suggestions = [
        "Should I water today?",
        "What should I watch next?",
        "Does this need repotting soon?",
    ]
    if latest_checkin and str(latest_checkin.get("health_status") or "") == "needs_care":
        suggestions.append("What should I do in the next 24 hours?")
    else:
        suggestions.append("What if this gets worse?")
    return suggestions[:4]


def heuristic_followup_answer(
    *,
    plant,
    question: str,
    recent_checkins: list[dict[str, object]] | None,
    focused_checkin: dict[str, object] | None = None,
    rolling_summary: str = "",
) -> dict[str, object]:
    anchor = focused_checkin or ((recent_checkins or [None])[0] if recent_checkins else None)
    anchor_title = str((anchor or {}).get("diagnosis_title") or "the latest read").strip()
    anchor_summary = str((anchor or {}).get("diagnosis_summary") or "").strip()
    care_steps = _clean_string_list((anchor or {}).get("care_steps") or [], limit=3, item_limit=100)
    question_text = _truncate_text(question, 180)

    if care_steps:
        answer = (
            f"Based on {plant['name']}'s recent read, I would treat this as a follow-up to {anchor_title.lower()}. "
            f"Start with {care_steps[0].lower()}"
        )
        if len(care_steps) > 1:
            answer += f", then {care_steps[1].lower()}."
        else:
            answer += "."
    elif anchor_summary:
        answer = (
            f"Based on the latest saved diagnosis for {plant['name']}, the main issue still looks like "
            f"{_truncate_text(anchor_summary, 180).lower()}"
        )
        if not answer.endswith("."):
            answer += "."
    else:
        answer = (
            f"I do not have enough saved detail to answer '{question_text}' very specifically yet. "
            f"Use the latest photo and note from {plant['name']} as the main guide, and save another check-in if anything changed."
        )

    rolling_bits = [rolling_summary.strip()] if rolling_summary.strip() else []
    rolling_bits.append(f"Recent follow-up topic: {question_text}")
    if anchor_title:
        rolling_bits.append(f"Recent diagnosis anchor: {anchor_title}")

    last_advice = care_steps[:2] if care_steps else [_truncate_text(answer, 120)]
    return {
        "answer": answer,
        "suggested_actions": care_steps[:3],
        "watch_signals": [],
        "rolling_summary": " ".join(bit for bit in rolling_bits if bit).strip(),
        "open_questions": [],
        "last_advice": last_advice,
    }


def answer_plant_followup(
    *,
    plant,
    question: str,
    recent_checkins: list[dict[str, object]] | None,
    recent_messages: list[dict[str, object]] | None,
    rolling_summary: str = "",
    focused_checkin: dict[str, object] | None = None,
) -> dict[str, object]:
    cleaned_question = str(question or "").strip()
    if not cleaned_question:
        raise RuntimeError("Follow-up question is empty.")

    if not live_model_available():
        log_model_event("fallback", flow="plant_followup", reason="live_model_unavailable")
        return heuristic_followup_answer(
            plant=plant,
            question=cleaned_question,
            recent_checkins=recent_checkins,
            focused_checkin=focused_checkin,
            rolling_summary=rolling_summary,
        )

    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "answer",
            "suggested_actions",
            "watch_signals",
            "rolling_summary",
            "open_questions",
            "last_advice",
        ],
        "properties": {
            "answer": {"type": "string"},
            "suggested_actions": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "watch_signals": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "rolling_summary": {"type": "string"},
            "open_questions": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
            "last_advice": {
                "type": "array",
                "maxItems": 3,
                "items": {"type": "string"},
            },
        },
    }

    system_prompt = (
        "You are a plant follow-up assistant inside a plant care app. "
        "The plant is already identified. Do not re-identify or rename the plant. "
        "Answer the user's follow-up question using the saved diagnosis history and recent chat context. "
        "Be concise, practical, and continuity-aware. "
        "Do not replay the whole history back to the user. "
        "Only mention prior context when it helps the next action. "
        "When uncertain, say what additional evidence would help."
    )
    chat_context = build_plant_chat_context(
        plant=plant,
        recent_checkins=recent_checkins,
        recent_messages=recent_messages,
        rolling_summary=rolling_summary,
        focused_checkin=focused_checkin,
    )

    user_prompt = (
        "Answer this plant follow-up question.\n\n"
        f"{chat_context}\n\n"
        f"User follow-up question: {cleaned_question}\n\n"
        "Return JSON only.\n"
        "Guidance:\n"
        "- answer: 1-3 short paragraphs or a few short bullets\n"
        "- suggested_actions: 0-3 concrete next steps for the next few days\n"
        "- watch_signals: 0-3 specific things to monitor\n"
        "- rolling_summary: update the plant chat memory in 1-3 short sentences\n"
        "- open_questions: unresolved follow-up questions, if any\n"
        "- last_advice: short reusable advice fragments from this answer"
    )

    try:
        parsed = call_structured_output(
            schema_name="plant_followup_answer",
            schema=schema,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image=None,
        )
    except RuntimeError as exc:
        log_model_event("fallback", flow="plant_followup", reason=str(exc)[:220])
        return heuristic_followup_answer(
            plant=plant,
            question=cleaned_question,
            recent_checkins=recent_checkins,
            focused_checkin=focused_checkin,
            rolling_summary=rolling_summary,
        )

    answer = _truncate_text(str(parsed.get("answer") or "").strip(), 900)
    if not answer:
        return heuristic_followup_answer(
            plant=plant,
            question=cleaned_question,
            recent_checkins=recent_checkins,
            focused_checkin=focused_checkin,
            rolling_summary=rolling_summary,
        )

    return {
        "answer": answer,
        "suggested_actions": _clean_string_list(parsed.get("suggested_actions"), limit=3, item_limit=240),
        "watch_signals": _clean_string_list(parsed.get("watch_signals"), limit=3, item_limit=240),
        "rolling_summary": _truncate_text(str(parsed.get("rolling_summary") or "").strip(), 420),
        "open_questions": _clean_string_list(parsed.get("open_questions"), limit=3, item_limit=180),
        "last_advice": _clean_string_list(parsed.get("last_advice"), limit=3, item_limit=180),
    }
