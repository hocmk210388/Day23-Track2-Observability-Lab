"""Write Slack webhook URL from .env into a one-line file for Alertmanager slack_api_url_file.

Docker Desktop on Windows often leaves {{ env "SLACK_WEBHOOK_URL" }} empty inside Alertmanager.
Mounting a file avoids that.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
OUT_PATH = ROOT / "02-prometheus-grafana" / "alertmanager" / "slack_url"
EXAMPLE = "https://hooks.slack.com/services/REPLACE/ME/HERE"


def read_slack_url_from_env() -> str:
    if not ENV_PATH.is_file():
        return EXAMPLE
    raw = ENV_PATH.read_text(encoding="utf-8-sig")
    m = re.search(r"^SLACK_WEBHOOK_URL\s*=\s*(\S+)\s*$", raw, re.MULTILINE)
    if not m:
        return EXAMPLE
    url = m.group(1).strip().strip('"').strip("'")
    if not url or url.startswith("#"):
        return EXAMPLE
    return url.rstrip()


def main() -> int:
    url = read_slack_url_from_env()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(url + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
