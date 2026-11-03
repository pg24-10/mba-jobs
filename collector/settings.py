"""Paths, config files and secrets."""

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
REFERENCE = ROOT / "reference"
DATA = ROOT / "data"
INBOX = DATA / "inbox"
TAGS = DATA / "tags"
LOGS = DATA / "logs"
STATE = DATA / "state"          # local, git-ignored: backfill checkpoints


@lru_cache
def config(name):
    with open(CONFIG / f"{name}.yaml") as f:
        return yaml.safe_load(f)


def load_env():
    """Read KEY=value lines from .env into the environment (without overriding)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def secret(name):
    load_env()
    value = os.environ.get(name, "")
    if not value:
        raise SystemExit(f"{name} is not set. Add it to .env (on the Mac) or GitHub Secrets.")
    return value


def machine():
    return "github" if os.environ.get("GITHUB_ACTIONS") == "true" else "mac"
