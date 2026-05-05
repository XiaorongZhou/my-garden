from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("MY_GARDEN_DB_PATH", str(ROOT / "my_garden.db"))).expanduser()
STATIC_DIR = ROOT / "static"
UPLOAD_DIR = Path(os.environ.get("MY_GARDEN_UPLOAD_DIR", str(ROOT / "uploads"))).expanduser()

AI_PROVIDER = os.environ.get("AI_PROVIDER", "openai").strip().lower()
AI_MODEL = os.environ.get("AI_MODEL", "").strip()
AI_BASE_URL = os.environ.get("AI_BASE_URL", "").strip()
AI_API_KEY = os.environ.get("AI_API_KEY", "").strip()
AI_TIMEOUT_SECONDS = float(os.environ.get("AI_TIMEOUT_SECONDS", os.environ.get("OPENAI_TIMEOUT_SECONDS", "25")))

OPENAI_RESPONSES_URL = os.environ.get("OPENAI_RESPONSES_URL", "https://api.openai.com/v1/responses")
OPENAI_PLANT_MODEL = os.environ.get("OPENAI_PLANT_MODEL", AI_MODEL or "gpt-5-mini")
OPENAI_TIMEOUT_SECONDS = AI_TIMEOUT_SECONDS
LOCAL_VLM_BASE_URL = os.environ.get("LOCAL_VLM_BASE_URL", AI_BASE_URL or "http://127.0.0.1:8000/v1").strip()
LOCAL_VLM_MODEL = os.environ.get("LOCAL_VLM_MODEL", AI_MODEL or "Qwen/Qwen2.5-VL-7B-Instruct").strip()
LOCAL_VLM_API_KEY = os.environ.get("LOCAL_VLM_API_KEY", AI_API_KEY).strip()
SUPPORTED_VISION_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SUPPORTED_VISION_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
HEIC_SUFFIXES = {".heic", ".heif"}
HEIC_MIME_TYPES = {"image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence"}

DEMO_MAIDENHAIR_ID = "795f41a2-7fc5-4d84-ae13-a71d4f4f22e1"
DEMO_CAT_PALM_ID = "92db1cd8-e07e-4e90-a95d-216f45a6bc42"
