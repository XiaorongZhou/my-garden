#!/usr/bin/env python3
"""My Garden app entrypoint."""

from __future__ import annotations

import os

from my_garden import run_server


if __name__ == "__main__":
    run_server(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
    )
