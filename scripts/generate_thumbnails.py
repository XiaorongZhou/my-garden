#!/usr/bin/env python3
"""Generate lightweight local thumbnails for existing uploaded plant photos."""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from my_garden.config import DB_PATH, UPLOAD_DIR
from my_garden.http_utils import thumbnail_name_for_photo_url


MAX_THUMBNAIL_SIDE = "360"


def upload_urls(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT cover_photo_url AS photo_url FROM plants WHERE cover_photo_url IS NOT NULL
        UNION
        SELECT photo_url FROM checkins WHERE photo_url IS NOT NULL
        """
    ).fetchall()
    urls = sorted({str(row[0]) for row in rows if str(row[0] or "").startswith("/uploads/")})
    return [url for url in urls if not url.rsplit("/", 1)[-1].startswith("thumb-")]


def generate_thumbnail(source: Path, destination: Path) -> bool:
    sips_path = shutil.which("sips")
    if not sips_path:
        raise SystemExit("This backfill script needs macOS `sips`; future app uploads create thumbnails in-browser.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".jpg", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        subprocess.run(
            [
                sips_path,
                "-Z",
                MAX_THUMBNAIL_SIDE,
                "-s",
                "format",
                "jpeg",
                str(source),
                "--out",
                str(tmp_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        tmp_path.replace(destination)
        return True
    except subprocess.CalledProcessError:
        tmp_path.unlink(missing_ok=True)
        return False


def main() -> None:
    if not DB_PATH.exists():
        raise SystemExit(f"Database not found: {DB_PATH}")

    generated = 0
    skipped = 0
    failed = 0
    with sqlite3.connect(DB_PATH) as connection:
        for url in upload_urls(connection):
            relative = url[len("/uploads/") :]
            source = UPLOAD_DIR / relative
            thumbnail_name = thumbnail_name_for_photo_url(url)
            if not thumbnail_name or not source.exists():
                skipped += 1
                continue
            destination = UPLOAD_DIR / thumbnail_name
            if destination.exists():
                skipped += 1
                continue
            if generate_thumbnail(source, destination):
                generated += 1
            else:
                failed += 1

    print(f"Generated {generated} thumbnails, skipped {skipped}, failed {failed}.")


if __name__ == "__main__":
    main()
