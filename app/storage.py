"""Private local storage. No listener, cloud database, or telemetry."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
from .model import Calendar

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = {"title": "Our week", "timezone": "Europe/London", "poll_seconds": 600,
                  "mask_private": True, "deduplicate": True, "calendars": []}


def data_dir() -> Path:
    override = os.environ.get("PAPERWEEK_DATA_DIR")
    path = Path(override).expanduser() if override else Path.home() / ".paperweek"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def atomic_write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".paperweek-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data.encode("utf-8") if isinstance(data, str) else data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        path.chmod(0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_config() -> dict:
    path = data_dir() / "config.json"
    config = dict(DEFAULT_CONFIG)
    if path.exists():
        config.update(json.loads(path.read_text()))
    if not isinstance(config["poll_seconds"], int) or not 60 <= config["poll_seconds"] <= 86400:
        raise ValueError("poll_seconds must be an integer between 60 and 86400.")
    for key in ("mask_private", "deduplicate"):
        if not isinstance(config[key], bool):
            raise ValueError(f"{key} must be true or false (not a quoted string).")
    if not isinstance(config["title"], str) or not config["title"].strip():
        raise ValueError("title must be a non-empty string.")
    from zoneinfo import ZoneInfo
    ZoneInfo(config["timezone"])
    calendars = [Calendar(**c) for c in config["calendars"]]
    if len(calendars) > 6 or len({c.id for c in calendars}) != len(calendars):
        raise ValueError("Choose up to six distinct calendars.")
    return config


def write_config(config: dict) -> None:
    atomic_write(data_dir() / "config.json", json.dumps(config, indent=2) + "\n")


def cache_key(config: dict, week: str) -> str:
    relevant = {key: config[key] for key in ("calendars", "timezone", "mask_private", "deduplicate")}
    # Privacy/config changes never reuse a differently filtered cache.
    return hashlib.sha256(json.dumps([relevant, week], sort_keys=True).encode()).hexdigest()[:24]
