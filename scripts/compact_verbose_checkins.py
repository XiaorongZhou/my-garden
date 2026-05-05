#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from my_garden.data import get_conn, init_db, json_dumps  # noqa: E402
from my_garden.plant_ai import (  # noqa: E402
    compact_imported_diagnosis,
    looks_like_verbose_chat_import,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rewrite verbose imported diagnoses into concise app copy."
    )
    parser.add_argument(
        "--user-email",
        required=True,
        help="Garden owner email whose diagnoses should be reviewed.",
    )
    parser.add_argument(
        "--plant-name",
        help="Optional plant name filter.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without writing to the database.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional limit on how many diagnoses to rewrite.",
    )
    return parser.parse_args()


def fetch_candidates(connection, *, user_email: str, plant_name: str | None) -> list[object]:
    query = """
        SELECT c.*, p.name AS plant_name, p.species AS plant_species, p.chinese_name AS plant_chinese_name
        FROM checkins c
        JOIN plants p ON p.id = c.plant_id
        JOIN users u ON u.id = p.user_id
        WHERE u.normalized_email = ?
        ORDER BY datetime(c.created_at) ASC
    """
    rows = connection.execute(query, (user_email.strip().lower(),)).fetchall()
    if plant_name:
        needle = plant_name.strip().lower()
        rows = [row for row in rows if needle in str(row["plant_name"]).strip().lower()]
    return [
        row
        for row in rows
        if looks_like_verbose_chat_import(
            str(row["diagnosis_title"] or ""),
            str(row["diagnosis_summary"] or ""),
        )
    ]


def preview_row(row, compacted) -> None:
    print("\n---")
    print(f"{row['plant_name']} | {row['created_at']} | {row['id']}")
    print(f"OLD TITLE: {row['diagnosis_title']}")
    print(f"NEW TITLE: {compacted['diagnosis_title']}")
    old_summary = str(row["diagnosis_summary"] or "").replace("\n", " ")
    new_summary = str(compacted["diagnosis_summary"] or "").replace("\n", " ")
    print(f"OLD SUMMARY: {old_summary[:240]}{'...' if len(old_summary) > 240 else ''}")
    print(f"NEW SUMMARY: {new_summary[:240]}{'...' if len(new_summary) > 240 else ''}")


def main() -> None:
    args = parse_args()
    init_db()
    updated = 0

    with get_conn() as connection:
        candidates = fetch_candidates(
            connection,
            user_email=args.user_email,
            plant_name=args.plant_name,
        )
        if args.limit > 0:
            candidates = candidates[: args.limit]

        if not candidates:
            print("No verbose imported diagnoses matched the filter.")
            return

        print(f"Found {len(candidates)} verbose diagnoses to rewrite.")
        for row in candidates:
            compacted = compact_imported_diagnosis(
                plant_name=str(row["plant_name"]),
                species=str(row["plant_species"]),
                chinese_name=str(row["plant_chinese_name"] or ""),
                owner_note=str(row["note"] or ""),
                diagnosis_title=str(row["diagnosis_title"] or ""),
                diagnosis_summary=str(row["diagnosis_summary"] or ""),
                care_steps=[],
                health_status=str(row["health_status"] or "watch"),
            )
            preview_row(row, compacted)
            if args.dry_run:
                continue

            connection.execute(
                """
                UPDATE checkins
                SET diagnosis_title = ?, diagnosis_summary = ?, care_steps_json = ?
                WHERE id = ?
                """,
                (
                    str(compacted["diagnosis_title"]),
                    str(compacted["diagnosis_summary"]),
                    json_dumps(list(compacted["care_steps"])),
                    str(row["id"]),
                ),
            )
            updated += 1

        if not args.dry_run:
            connection.commit()

    if args.dry_run:
        print(f"\nDry run only. Would rewrite {len(candidates)} diagnoses.")
        return
    print(f"\nRewrote {updated} diagnoses.")


if __name__ == "__main__":
    main()
