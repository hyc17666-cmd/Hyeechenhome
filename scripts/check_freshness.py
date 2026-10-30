#!/usr/bin/env python3
"""Check whether the site already contains complete data for today."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHINA_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
DEFAULT_DATA_FILE = Path("site/data/articles.json")
EXPECTED_SOURCES = {"people", "guangming", "economic", "qiushi"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-file", type=Path, default=DEFAULT_DATA_FILE)
    parser.add_argument("--today", help="Override today's date for testing (YYYY-MM-DD)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    today = args.today or datetime.now(CHINA_TZ).date().isoformat()

    try:
        data = json.loads(args.data_file.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        data = {}

    generated_at = str(data.get("generated_at") or "")
    latest_paper_date = str(data.get("latest_paper_date") or "")
    statuses = data.get("sources_status") or []
    source_keys = {str(item.get("source_key")) for item in statuses if isinstance(item, dict)}

    generated_today = generated_at[:10] == today
    paper_current = latest_paper_date == today
    sources_complete = EXPECTED_SOURCES.issubset(source_keys)
    sources_ok = sources_complete and all(
        item.get("status") == "ok" and str(item.get("paper_date") or "") == today
        for item in statuses
        if isinstance(item, dict)
    )
    has_articles = int(data.get("total") or 0) > 0
    needed = not (generated_today and paper_current and sources_ok and has_articles)

    outputs = {
        "needed": "true" if needed else "false",
        "generated_at": generated_at,
        "latest_paper_date": latest_paper_date,
        "sources_ok": "true" if sources_ok else "false",
    }
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            for key, value in outputs.items():
                output.write(f"{key}={value}\n")

    summary = (
        f"today={today}; generated_at={generated_at or 'missing'}; "
        f"latest_paper_date={latest_paper_date or 'missing'}; "
        f"sources_ok={str(sources_ok).lower()}; has_articles={str(has_articles).lower()}; "
        f"update_needed={str(needed).lower()}"
    )
    print(summary)
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as output:
            output.write(f"### Daily data check\n\n`{summary}`\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
