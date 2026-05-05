#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from my_garden.data import (  # noqa: E402
    create_checkin,
    create_plant,
    fetch_plant_row,
    get_conn,
    init_db,
    list_plant_rows_for_user,
    make_plant_id,
)
from my_garden.plant_ai import default_tip_for_identity, heuristic_chinese_name  # noqa: E402
from my_garden.plant_ai import compact_imported_diagnosis  # noqa: E402


USER_AGENT = "MyGardenImporter/1.0 (+https://github.com/XiaorongZhou/my-garden)"
STREAM_PATTERN = re.compile(r'streamController\.enqueue\("(.+?)"\);</script>', re.S)
TITLE_PATTERN = re.compile(r"<title>ChatGPT - (.*?)</title>", re.I | re.S)
UUID_PATTERN = re.compile(r'"([0-9a-f]{8}-[0-9a-f-]{27})"')
TIMESTAMP_PATTERN = re.compile(r"(1\d{9}\.\d+)")
IMAGE_FILENAME_PATTERN = re.compile(r"\.(?:jpe?g|png|gif|webp|heic|heif)$", re.I)
INLINE_WIDGET_PATTERN = re.compile(r"[^]{0,4000}?", re.S)
PRIVATE_WIDGET_PATTERN = re.compile(r"[\ue200-\ue2ff][^\ue200-\ue2ff]{0,4000}?[\ue200-\ue2ff]", re.S)
NON_HUMAN_NOTE_VALUES = {
    "attachments",
    "triggered_by_system_hint_suggestion",
}

PLANT_CATALOG = [
    {
        "key": "green-onion",
        "name": "Green Onion",
        "species": "Allium fistulosum (likely)",
        "chinese_name": "小葱",
        "aliases": ["green onion", "scallion", "spring onion", "小葱"],
    },
    {
        "key": "shallot",
        "name": "Shallot",
        "species": "Allium cepa var. aggregatum (likely)",
        "chinese_name": "红葱头",
        "aliases": ["shallot", "red shallot", "红葱头", "红葱"],
    },
    {
        "key": "maidenhair-fern",
        "name": "Maidenhair Fern",
        "species": "Adiantum raddianum",
        "chinese_name": "铁线蕨",
        "aliases": ["maidenhair fern", "adiantum", "铁线蕨"],
    },
    {
        "key": "cat-palm",
        "name": "Cat Palm",
        "species": "Chamaedorea cataractarum",
        "chinese_name": "猫棕",
        "aliases": ["cat palm", "chamaedorea cataractarum", "猫棕"],
    },
    {
        "key": "dragon-fruit",
        "name": "Dragon Fruit Cactus",
        "species": "Selenicereus undatus (likely)",
        "chinese_name": "火龙果",
        "aliases": ["dragon fruit", "pitaya", "火龙果"],
    },
    {
        "key": "spider-plant",
        "name": "Spider Plant",
        "species": "Chlorophytum comosum",
        "chinese_name": "吊兰",
        "aliases": ["spider plant", "chlorophytum", "吊兰"],
    },
    {
        "key": "succulent",
        "name": "Succulent",
        "species": "Unknown succulent",
        "chinese_name": "多肉植物",
        "aliases": ["succulent", "graptopetalum", "graptoveria", "多肉"],
    },
    {
        "key": "snake-plant",
        "name": "Snake Plant",
        "species": "Dracaena trifasciata",
        "chinese_name": "虎尾兰",
        "aliases": ["snake plant", "sansevieria", "dracaena trifasciata", "虎尾兰"],
    },
    {
        "key": "pothos",
        "name": "Pothos",
        "species": "Epipremnum aureum",
        "chinese_name": "绿萝",
        "aliases": ["pothos", "epipremnum", "绿萝"],
    },
]


@dataclass
class CandidateTurn:
    role: str
    text: str
    timestamp: float
    message_id: str
    source_offset: int


@dataclass
class ImportableCheckin:
    note: str
    diagnosis_text: str
    created_at: str
    message_id: str


@dataclass
class PlantTarget:
    key: str
    name: str
    species: str
    chinese_name: str
    aliases: tuple[str, ...]
    plant_id: str | None
    location: str
    match_type: str


@dataclass
class PlannedDiagnosis:
    checkin: ImportableCheckin
    match_strategy: str
    matched_aliases: list[str]


@dataclass
class GroupedPlantImport:
    target: PlantTarget
    items: list[PlannedDiagnosis]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import one ChatGPT shared thread into My Garden check-ins."
    )
    parser.add_argument(
        "--share-url",
        required=True,
        help="ChatGPT share URL, e.g. https://chatgpt.com/share/...",
    )
    parser.add_argument(
        "--user-email",
        required=True,
        help="Garden owner email already registered in My Garden.",
    )
    parser.add_argument("--plant-id", help="Plant UUID to import into.")
    parser.add_argument(
        "--plant-name",
        help="Plant name to import into (case-insensitive exact match or substring).",
    )
    parser.add_argument(
        "--all-plants",
        action="store_true",
        help="Group the whole thread across all detected plants instead of forcing one destination plant.",
    )
    parser.add_argument(
        "--create-missing-plants",
        action="store_true",
        help="When used with --all-plants, create missing plants before importing their diagnoses.",
    )
    parser.add_argument(
        "--json-preview",
        help="Optional path for a structured preview JSON file. Use - to print JSON to stdout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print extracted check-ins without writing to the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on number of extracted assistant diagnoses.",
    )
    args = parser.parse_args()
    if args.all_plants and (args.plant_id or args.plant_name):
        parser.error("--all-plants cannot be combined with --plant-id or --plant-name.")
    if not args.all_plants and not (args.plant_id or args.plant_name):
        parser.error("Pick a target plant with --plant-id or --plant-name, or use --all-plants.")
    if args.create_missing_plants and not args.all_plants:
        parser.error("--create-missing-plants only makes sense together with --all-plants.")
    return args


def fetch_share_html(share_url: str) -> str:
    request = urllib.request.Request(
        share_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", "ignore")


def extract_share_title(raw_html: str) -> str:
    match = TITLE_PATTERN.search(raw_html)
    if not match:
        return "Imported ChatGPT thread"
    return html.unescape(match.group(1)).strip()


def decode_stream_payloads(raw_html: str) -> str:
    matches = STREAM_PATTERN.findall(raw_html)
    if not matches:
        raise SystemExit("Could not find the shared conversation payload in that ChatGPT page.")
    return "".join(json.loads(f'"{chunk}"') for chunk in matches)


def looks_like_human_turn(text: str) -> bool:
    cleaned = text.strip()
    if len(cleaned) < 8:
        return False
    if cleaned.startswith(("http://", "https://", "sediment://", "file_", "P5071:", "GLOBAL")):
        return False
    if cleaned.startswith(("routes/share", "create_time", "update_time", "moderationMode")):
        return False
    if "private-repo" in cleaned or "docs.google.com" in cleaned:
        return False
    if cleaned.count("_") > 8:
        return False
    if IMAGE_FILENAME_PATTERN.search(cleaned) and "/" not in cleaned and " " not in cleaned:
        return False
    if cleaned in {
        "children",
        "assistant",
        "real_author",
        "tool:web",
        "language",
        "mime_type",
        "image/jpeg",
        "multimodal_text",
        "image_asset_pointer",
        "asset_pointer",
        "size_bytes",
        "sanitized",
        "is_redacted",
        "model_editable_context",
        "model_set_context",
        "rebase_system_message",
        "rebase_developer_message",
        "dictation",
        "message_source",
    }:
        return False
    if len(cleaned) == 36 and re.fullmatch(r"[0-9a-f-]{36}", cleaned):
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z]", cleaned))


def classify_turn_role(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) >= 180:
        return "assistant"
    if cleaned.count("\n") >= 3:
        return "assistant"
    if any(token in cleaned for token in ("---", "###", "## ", "👉", "✅", "🌱", "🧠", "结论", "步骤")):
        return "assistant"
    if len(cleaned) <= 140:
        return "user"
    return "skip"


def extract_turn_candidates(decoded_stream: str) -> list[CandidateTurn]:
    candidates: list[CandidateTurn] = []
    seen_keys: set[tuple[str, str, int]] = set()

    for match in re.finditer(r'"((?:\\.|[^"\\]){8,})"', decoded_stream):
        try:
            text = json.loads(f'"{match.group(1)}"').strip()
        except json.JSONDecodeError:
            continue
        if not looks_like_human_turn(text):
            continue

        role = classify_turn_role(text)
        if role == "skip":
            continue

        window_after = decoded_stream[match.end() : match.end() + 900]
        uuid_match = UUID_PATTERN.search(window_after)
        ts_match = TIMESTAMP_PATTERN.search(window_after)
        if not uuid_match or not ts_match:
            continue

        timestamp = float(ts_match.group(1))
        message_id = uuid_match.group(1)
        key = (role, message_id, int(timestamp))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidates.append(
            CandidateTurn(
                role=role,
                text=text,
                timestamp=timestamp,
                message_id=message_id,
                source_offset=match.start(),
            )
        )

    return candidates


def sanitize_chatgpt_text(text: str) -> str:
    cleaned = INLINE_WIDGET_PATTERN.sub("", text)
    cleaned = PRIVATE_WIDGET_PATTERN.sub("", cleaned)
    cleaned = cleaned.replace("\ufeff", "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def sanitize_user_note(text: str) -> str:
    cleaned = sanitize_chatgpt_text(text)
    if normalize_alias(cleaned) in NON_HUMAN_NOTE_VALUES:
        return ""
    return cleaned


def build_importable_checkins(candidates: list[CandidateTurn]) -> list[ImportableCheckin]:
    ordered = sorted(candidates, key=lambda item: (item.timestamp, item.source_offset))
    latest_user_by_time: list[CandidateTurn] = []
    imports: list[ImportableCheckin] = []

    for turn in ordered:
        if turn.role == "user":
            latest_user_by_time.append(turn)
            continue

        note = ""
        for user_turn in reversed(latest_user_by_time):
            if user_turn.timestamp <= turn.timestamp:
                note = user_turn.text
                break

        created_at = datetime.fromtimestamp(turn.timestamp, tz=timezone.utc).isoformat(
            timespec="seconds"
        )
        imports.append(
            ImportableCheckin(
                note=sanitize_user_note(note),
                diagnosis_text=sanitize_chatgpt_text(turn.text),
                created_at=created_at,
                message_id=turn.message_id,
            )
        )

    deduped: list[ImportableCheckin] = []
    seen: set[str] = set()
    for item in imports:
        digest = hashlib.sha1(
            f"{item.created_at}|{item.note}|{item.diagnosis_text}".encode("utf-8")
        ).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        deduped.append(item)
    return deduped


def clean_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^[\-\*\u2022]+\s*", "", line)
    line = re.sub(r"^\d+[.)]\s*", "", line)
    line = line.replace("👉", "").replace("✅", "").replace("⚠️", "").replace("🌟", "")
    return line.strip()


def diagnosis_title(text: str) -> str:
    for raw_line in text.splitlines():
        line = clean_line(raw_line)
        if line:
            return line[:120]
    return "Imported ChatGPT diagnosis"


def diagnosis_summary(text: str) -> str:
    stripped = text.strip()
    return stripped[:2500]


def extract_care_steps(text: str) -> list[str]:
    steps: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^([\-\*\u2022]|\d+[.)])\s+", line):
            cleaned = clean_line(line)
            if cleaned and cleaned not in steps:
                steps.append(cleaned[:220])
    return steps[:8]


def infer_health_status(text: str) -> str:
    lower = text.lower()
    if any(
        token in lower
        for token in ["烂根", "needs water", "need water", "brown", "crispy", "stress", "黄", "蔫", "枯"]
    ):
        return "needs_care"
    if any(token in lower for token in ["恢复", "healthy", "thriving", "成功", "理想", "稳定", "长得很好"]):
        return "thriving"
    return "watch"


def resolve_user(connection, email: str):
    normalized = email.strip().lower()
    row = connection.execute(
        "SELECT * FROM users WHERE normalized_email = ?",
        (normalized,),
    ).fetchone()
    if row is None:
        raise SystemExit(
            f"No My Garden user found for {email}. Open the app first and sign in with that email."
        )
    return row


def resolve_plant(connection, user_id: str, plant_id: str | None, plant_name: str | None):
    if plant_id:
        return fetch_plant_row(connection, plant_id, user_id=user_id)

    rows = list_plant_rows_for_user(connection, user_id)
    if not plant_name:
        names = ", ".join(str(row["name"]) for row in rows)
        raise SystemExit(f"Pick a target plant with --plant-id or --plant-name. Available plants: {names}")

    exact_matches = [
        row for row in rows if str(row["name"]).strip().lower() == plant_name.strip().lower()
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    partial_matches = [
        row for row in rows if plant_name.strip().lower() in str(row["name"]).strip().lower()
    ]
    if len(partial_matches) == 1:
        return partial_matches[0]

    if not partial_matches and not exact_matches:
        names = ", ".join(str(row["name"]) for row in rows)
        raise SystemExit(f"Could not find a plant named {plant_name!r}. Available plants: {names}")

    matches = exact_matches or partial_matches
    names = ", ".join(f"{row['name']} ({row['id']})" for row in matches)
    raise SystemExit(
        f"Plant name {plant_name!r} matched multiple plants: {names}. Use --plant-id instead."
    )


def make_checkin_id(share_url: str, message_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{share_url}#{message_id}"))


def normalize_alias(value: str) -> str:
    return str(value or "").strip().lower()


def merge_aliases(*collections: object) -> tuple[str, ...]:
    aliases: list[str] = []
    seen: set[str] = set()
    for collection in collections:
        if collection is None:
            continue
        if isinstance(collection, (list, tuple, set)):
            values = collection
        else:
            values = [collection]
        for raw in values:
            alias = normalize_alias(str(raw or ""))
            if len(alias) < 2:
                continue
            if alias in seen:
                continue
            seen.add(alias)
            aliases.append(alias)
    aliases.sort(key=len, reverse=True)
    return tuple(aliases)


def alias_score(alias: str) -> int:
    if re.search(r"[a-z]", alias):
        return min(12, max(3, len(alias)))
    return max(6, len(alias) * 3)


def make_target_from_catalog(entry: dict[str, object]) -> PlantTarget:
    return PlantTarget(
        key=str(entry["key"]),
        name=str(entry["name"]),
        species=str(entry["species"]),
        chinese_name=str(entry["chinese_name"]),
        aliases=merge_aliases(entry["aliases"], entry["name"], entry["species"], entry["chinese_name"]),
        plant_id=None,
        location="",
        match_type="suggested",
    )


def target_for_existing_row(row) -> PlantTarget:
    return PlantTarget(
        key=f"existing:{row['id']}",
        name=str(row["name"]),
        species=str(row["species"]),
        chinese_name=str(row["chinese_name"] or ""),
        aliases=merge_aliases(row["name"], row["species"], row["chinese_name"]),
        plant_id=str(row["id"]),
        location=str(row["location"] or ""),
        match_type="existing",
    )


def best_catalog_key_for_row(row) -> str | None:
    haystack = " ".join(
        [
            normalize_alias(row["name"]),
            normalize_alias(row["species"]),
            normalize_alias(row["chinese_name"]),
        ]
    )
    best_key: str | None = None
    best_score = 0
    for entry in PLANT_CATALOG:
        aliases = merge_aliases(entry["aliases"], entry["name"], entry["species"], entry["chinese_name"])
        matched = [alias for alias in aliases if alias in haystack]
        score = sum(alias_score(alias) for alias in matched)
        if score > best_score:
            best_key = str(entry["key"])
            best_score = score
    return best_key


def build_targets(plant_rows: list[object]) -> dict[str, PlantTarget]:
    targets: dict[str, PlantTarget] = {
        str(entry["key"]): make_target_from_catalog(entry) for entry in PLANT_CATALOG
    }
    for row in plant_rows:
        catalog_key = best_catalog_key_for_row(row)
        if catalog_key and catalog_key in targets:
            base = targets[catalog_key]
            targets[catalog_key] = PlantTarget(
                key=catalog_key,
                name=str(row["name"]),
                species=str(row["species"]),
                chinese_name=str(row["chinese_name"] or ""),
                aliases=merge_aliases(
                    base.aliases,
                    row["name"],
                    row["species"],
                    row["chinese_name"],
                ),
                plant_id=str(row["id"]),
                location=str(row["location"] or ""),
                match_type="existing",
            )
            continue

        fallback = target_for_existing_row(row)
        targets[fallback.key] = fallback
    return targets


def match_target_for_checkin(
    checkin: ImportableCheckin,
    targets: dict[str, PlantTarget],
    *,
    previous_target_key: str | None,
    previous_timestamp: datetime | None,
) -> tuple[str | None, str, list[str]]:
    note_haystack = normalize_alias(checkin.note)
    diagnosis_haystack = normalize_alias(checkin.diagnosis_text)
    haystack = f"{note_haystack}\n{diagnosis_haystack}"
    best_target_key: str | None = None
    best_aliases: list[str] = []
    best_score = 0

    for target in targets.values():
        matched_aliases = [alias for alias in target.aliases if alias in haystack]
        if not matched_aliases:
            continue

        note_matches = [alias for alias in matched_aliases if alias in note_haystack]
        diagnosis_matches = [alias for alias in matched_aliases if alias in diagnosis_haystack]
        score = sum(alias_score(alias) for alias in set(matched_aliases))
        if note_matches:
            score += 12 * len(set(note_matches))
        if diagnosis_matches:
            first_position = min(diagnosis_haystack.find(alias) for alias in diagnosis_matches)
            if first_position >= 0:
                score += max(0, 120 - min(first_position, 120)) // 6
        if target.match_type == "existing":
            score += 2
        if score > best_score:
            best_score = score
            best_target_key = target.key
            best_aliases = sorted(set(matched_aliases), key=len, reverse=True)[:4]

    if best_target_key is not None:
        return best_target_key, "alias", best_aliases

    current_timestamp = datetime.fromisoformat(checkin.created_at)
    if previous_target_key and previous_timestamp:
        delta_seconds = (current_timestamp - previous_timestamp).total_seconds()
        if 0 <= delta_seconds <= 1800:
            return previous_target_key, "carry-forward", []

    return None, "unmatched", []


def group_checkins_by_plant(
    checkins: list[ImportableCheckin],
    targets: dict[str, PlantTarget],
) -> tuple[list[GroupedPlantImport], list[PlannedDiagnosis]]:
    grouped: dict[str, GroupedPlantImport] = {}
    unmatched: list[PlannedDiagnosis] = []
    previous_target_key: str | None = None
    previous_timestamp: datetime | None = None
    assignments: list[tuple[ImportableCheckin, str | None, str, list[str]]] = []

    for checkin in checkins:
        target_key, strategy, aliases = match_target_for_checkin(
            checkin,
            targets,
            previous_target_key=previous_target_key,
            previous_timestamp=previous_timestamp,
        )
        assignments.append((checkin, target_key, strategy, aliases))
        previous_target_key = target_key
        previous_timestamp = datetime.fromisoformat(checkin.created_at) if target_key else previous_timestamp

    for index, (checkin, target_key, strategy, aliases) in enumerate(assignments):
        if target_key is None and not checkin.note:
            current_time = datetime.fromisoformat(checkin.created_at)
            next_target_key: str | None = None
            next_delta: float | None = None
            for later_checkin, later_target_key, _, _ in assignments[index + 1 :]:
                if later_target_key is None:
                    continue
                next_time = datetime.fromisoformat(later_checkin.created_at)
                next_delta = (next_time - current_time).total_seconds()
                next_target_key = later_target_key
                break
            if next_target_key and next_delta is not None and 0 <= next_delta <= 900:
                target_key = next_target_key
                strategy = "lookahead-attachment"
                aliases = []

        planned = PlannedDiagnosis(
            checkin=checkin,
            match_strategy=strategy,
            matched_aliases=aliases,
        )
        if target_key is None:
            unmatched.append(planned)
            continue

        group = grouped.setdefault(
            target_key,
            GroupedPlantImport(target=targets[target_key], items=[]),
        )
        group.items.append(planned)

    return sorted(grouped.values(), key=lambda group: (-len(group.items), group.target.name)), unmatched


def serialize_planned_diagnosis(item: PlannedDiagnosis) -> dict[str, object]:
    return {
        "created_at": item.checkin.created_at,
        "message_id": item.checkin.message_id,
        "note": item.checkin.note,
        "diagnosis_title": diagnosis_title(item.checkin.diagnosis_text),
        "diagnosis_summary": diagnosis_summary(item.checkin.diagnosis_text),
        "care_steps": extract_care_steps(item.checkin.diagnosis_text),
        "health_status": infer_health_status(item.checkin.diagnosis_text),
        "match_strategy": item.match_strategy,
        "matched_aliases": item.matched_aliases,
    }


def serialize_target(target: PlantTarget) -> dict[str, object]:
    return {
        "key": target.key,
        "id": target.plant_id,
        "name": target.name,
        "species": target.species,
        "chinese_name": target.chinese_name,
        "location": target.location,
        "match_type": target.match_type,
        "aliases": list(target.aliases),
    }


def build_preview_payload(
    *,
    title: str,
    share_url: str,
    mode: str,
    grouped: list[GroupedPlantImport],
    unmatched: list[PlannedDiagnosis],
) -> dict[str, object]:
    return {
        "thread_title": title,
        "share_url": share_url,
        "mode": mode,
        "total_diagnoses": sum(len(group.items) for group in grouped) + len(unmatched),
        "groups": [
            {
                "target": serialize_target(group.target),
                "diagnosis_count": len(group.items),
                "diagnoses": [serialize_planned_diagnosis(item) for item in group.items],
            }
            for group in grouped
        ],
        "unmatched": [serialize_planned_diagnosis(item) for item in unmatched],
    }


def write_json_preview(preview: dict[str, object], output_path: str) -> None:
    rendered = json.dumps(preview, ensure_ascii=False, indent=2)
    if output_path == "-":
        print("\nJSON preview:")
        print(rendered)
        return

    path = Path(output_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + "\n", encoding="utf-8")
    print(f"\nWrote JSON preview to {path}")


def preview_grouped_checkins(title: str, grouped: list[GroupedPlantImport], unmatched: list[PlannedDiagnosis]) -> None:
    total = sum(len(group.items) for group in grouped) + len(unmatched)
    print(f"\nThread: {title}")
    print(f"Extracted assistant diagnoses: {total}")
    print(f"Detected plant groups: {len(grouped)}")
    for group in grouped:
        target = group.target
        label = target.name
        if target.chinese_name:
            label = f"{label} / {target.chinese_name}"
        print(f"\n- {label} [{target.match_type}] -> {len(group.items)} diagnoses")
        for item in group.items[:2]:
            print(f"  {item.checkin.created_at} | {diagnosis_title(item.checkin.diagnosis_text)}")
            if item.matched_aliases:
                print(f"    matched by: {', '.join(item.matched_aliases)}")
    if unmatched:
        print(f"\nUnmatched diagnoses: {len(unmatched)}")
        for item in unmatched[:3]:
            print(f"  {item.checkin.created_at} | {diagnosis_title(item.checkin.diagnosis_text)}")


def preview_single_target(title: str, target: PlantTarget, checkins: list[ImportableCheckin]) -> None:
    print(f"\nThread: {title}")
    print(f"Target plant: {target.name}")
    print(f"Extracted assistant diagnoses: {len(checkins)}")
    for item in checkins[:3]:
        print("\n---")
        print(item.created_at)
        print("User note:", item.note[:180] if item.note else "(none)")
        print("Diagnosis title:", diagnosis_title(item.diagnosis_text))
        summary = diagnosis_summary(item.diagnosis_text).replace("\n", " ")
        print("Summary:", summary[:240] + ("..." if len(summary) > 240 else ""))


def ensure_target_plant(
    connection,
    *,
    user_id: str,
    target: PlantTarget,
    created_at: str,
    create_missing_plants: bool,
) -> tuple[str | None, bool]:
    if target.plant_id:
        return target.plant_id, False
    if not create_missing_plants:
        return None, False

    plant_id = make_plant_id(connection)
    tip = default_tip_for_identity(name=target.name, species=target.species)
    tip_title = str(tip["title"]) if tip else ""
    tip_body = str(tip["body"]) if tip else ""
    tip_source = str(tip["source"]) if tip else "empty"
    chinese_name = target.chinese_name or heuristic_chinese_name(
        name=target.name,
        species=target.species,
    )
    create_plant(
        connection,
        plant_id=plant_id,
        user_id=user_id,
        name=target.name,
        species=target.species,
        chinese_name=chinese_name,
        location=target.location,
        notes="",
        note_origin="empty",
        tip_title=tip_title,
        tip_body=tip_body,
        tip_source=tip_source,
        cover_photo_url=None,
        created_at=created_at,
    )
    target.plant_id = plant_id
    target.chinese_name = chinese_name
    target.match_type = "created"
    return plant_id, True


def import_checkins(
    *,
    share_url: str,
    checkins: list[ImportableCheckin],
    plant_id: str,
    dry_run: bool,
) -> tuple[int, int]:
    inserted = 0
    skipped = 0
    with get_conn() as connection:
        plant_row = fetch_plant_row(connection, plant_id)
        for item in checkins:
            checkin_id = make_checkin_id(share_url, item.message_id)
            exists = connection.execute(
                "SELECT 1 FROM checkins WHERE id = ?",
                (checkin_id,),
            ).fetchone()
            if exists:
                skipped += 1
                continue

            if dry_run:
                inserted += 1
                continue

            compacted = compact_imported_diagnosis(
                plant_name=str(plant_row["name"]),
                species=str(plant_row["species"]),
                chinese_name=str(plant_row["chinese_name"] or ""),
                owner_note=item.note,
                diagnosis_title=diagnosis_title(item.diagnosis_text),
                diagnosis_summary=diagnosis_summary(item.diagnosis_text),
                care_steps=extract_care_steps(item.diagnosis_text),
                health_status=infer_health_status(item.diagnosis_text),
            )
            create_checkin(
                connection,
                checkin_id=checkin_id,
                plant_id=plant_id,
                note=item.note,
                photo_url=None,
                health_status=str(compacted["health_status"]),
                diagnosis_title=str(compacted["diagnosis_title"]),
                diagnosis_summary=str(compacted["diagnosis_summary"]),
                care_steps=list(compacted["care_steps"]),
                created_at=item.created_at,
            )
            inserted += 1
        if not dry_run:
            connection.commit()
    return inserted, skipped


def import_grouped_checkins(
    *,
    share_url: str,
    grouped: list[GroupedPlantImport],
    user_id: str,
    dry_run: bool,
    create_missing_plants: bool,
) -> dict[str, int]:
    inserted = 0
    skipped_duplicates = 0
    skipped_uncreated = 0
    created_plants = 0

    with get_conn() as connection:
        for group in grouped:
            first_created_at = group.items[0].checkin.created_at
            plant_id, created = ensure_target_plant(
                connection,
                user_id=user_id,
                target=group.target,
                created_at=first_created_at,
                create_missing_plants=create_missing_plants and not dry_run,
            )
            if created:
                created_plants += 1
            if plant_id is None:
                skipped_uncreated += len(group.items)
                continue

            plant_row = fetch_plant_row(connection, plant_id)

            for planned in group.items:
                item = planned.checkin
                checkin_id = make_checkin_id(share_url, item.message_id)
                exists = connection.execute(
                    "SELECT 1 FROM checkins WHERE id = ?",
                    (checkin_id,),
                ).fetchone()
                if exists:
                    skipped_duplicates += 1
                    continue

                if dry_run:
                    inserted += 1
                    continue

                compacted = compact_imported_diagnosis(
                    plant_name=str(plant_row["name"]),
                    species=str(plant_row["species"]),
                    chinese_name=str(plant_row["chinese_name"] or ""),
                    owner_note=item.note,
                    diagnosis_title=diagnosis_title(item.diagnosis_text),
                    diagnosis_summary=diagnosis_summary(item.diagnosis_text),
                    care_steps=extract_care_steps(item.diagnosis_text),
                    health_status=infer_health_status(item.diagnosis_text),
                )
                create_checkin(
                    connection,
                    checkin_id=checkin_id,
                    plant_id=plant_id,
                    note=item.note,
                    photo_url=None,
                    health_status=str(compacted["health_status"]),
                    diagnosis_title=str(compacted["diagnosis_title"]),
                    diagnosis_summary=str(compacted["diagnosis_summary"]),
                    care_steps=list(compacted["care_steps"]),
                    created_at=item.created_at,
                )
                inserted += 1

        if not dry_run:
            connection.commit()

    return {
        "inserted": inserted,
        "skipped_duplicates": skipped_duplicates,
        "skipped_uncreated": skipped_uncreated,
        "created_plants": created_plants,
    }


def main() -> None:
    args = parse_args()
    init_db()

    raw_html = fetch_share_html(args.share_url)
    title = extract_share_title(raw_html)
    decoded_stream = decode_stream_payloads(raw_html)
    candidates = extract_turn_candidates(decoded_stream)
    checkins = build_importable_checkins(candidates)
    if args.limit > 0:
        checkins = checkins[: args.limit]

    if not checkins:
        raise SystemExit("I could not extract any assistant diagnoses from that shared thread.")

    with get_conn() as connection:
        user_row = resolve_user(connection, args.user_email)
        user_id = str(user_row["id"])
        plant_rows = list_plant_rows_for_user(connection, user_id)

        if args.all_plants:
            targets = build_targets(plant_rows)
            grouped, unmatched = group_checkins_by_plant(checkins, targets)
            preview_grouped_checkins(title, grouped, unmatched)
            preview_payload = build_preview_payload(
                title=title,
                share_url=args.share_url,
                mode="all-plants",
                grouped=grouped,
                unmatched=unmatched,
            )
            if args.json_preview:
                write_json_preview(preview_payload, args.json_preview)

            stats = import_grouped_checkins(
                share_url=args.share_url,
                grouped=grouped,
                user_id=user_id,
                dry_run=args.dry_run,
                create_missing_plants=args.create_missing_plants,
            )
            if args.dry_run:
                print(
                    f"\nDry run only. Would import {stats['inserted']} diagnoses, "
                    f"skip {stats['skipped_duplicates']} duplicates, "
                    f"and leave {stats['skipped_uncreated']} diagnoses waiting on missing plants."
                )
                return

            print(
                f"\nImported {stats['inserted']} diagnoses across {len(grouped)} plant groups. "
                f"Skipped {stats['skipped_duplicates']} duplicates."
            )
            if stats["created_plants"]:
                print(f"Created {stats['created_plants']} new plants during import.")
            if stats["skipped_uncreated"]:
                print(
                    f"Skipped {stats['skipped_uncreated']} diagnoses because those plants do not exist yet. "
                    f"Re-run with --create-missing-plants to create them automatically."
                )
            return

        plant_row = resolve_plant(
            connection,
            user_id,
            args.plant_id,
            args.plant_name,
        )
        target = PlantTarget(
            key=f"existing:{plant_row['id']}",
            name=str(plant_row["name"]),
            species=str(plant_row["species"]),
            chinese_name=str(plant_row["chinese_name"] or ""),
            aliases=merge_aliases(plant_row["name"], plant_row["species"], plant_row["chinese_name"]),
            plant_id=str(plant_row["id"]),
            location=str(plant_row["location"] or ""),
            match_type="existing",
        )

    preview_single_target(title, target, checkins)
    if args.json_preview:
        grouped = [
            GroupedPlantImport(
                target=target,
                items=[
                    PlannedDiagnosis(
                        checkin=item,
                        match_strategy="forced-target",
                        matched_aliases=[],
                    )
                    for item in checkins
                ],
            )
        ]
        preview_payload = build_preview_payload(
            title=title,
            share_url=args.share_url,
            mode="single-plant",
            grouped=grouped,
            unmatched=[],
        )
        write_json_preview(preview_payload, args.json_preview)

    inserted, skipped = import_checkins(
        share_url=args.share_url,
        checkins=checkins,
        plant_id=str(target.plant_id),
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(f"\nDry run only. Would import {inserted} check-ins and skip {skipped} duplicates.")
        return

    print(f"\nImported {inserted} check-ins into {target.name}. Skipped {skipped} duplicates.")


if __name__ == "__main__":
    main()
