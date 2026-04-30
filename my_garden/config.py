from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
