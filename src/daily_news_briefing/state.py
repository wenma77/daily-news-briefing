from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from .models import SeenEvent
from .utils import parse_datetime, utc_now


def load_seen_events(path: Path) -> list[SeenEvent]:
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    results: list[SeenEvent] = []
    for item in raw.get("items", []):
        sent_at = parse_datetime(item.get("sent_at"))
        if not sent_at:
            continue
        results.append(
            SeenEvent(
                fingerprint=item.get("fingerprint", ""),
                title=item.get("title", ""),
                sent_at=sent_at,
            )
        )
    return results


def prune_seen_events(events: list[SeenEvent], retention_days: int = 3) -> list[SeenEvent]:
    cutoff = utc_now() - timedelta(days=retention_days)
    return [item for item in events if item.sent_at >= cutoff]


def recent_fingerprints(events: list[SeenEvent], retention_days: int = 3) -> set[str]:
    return {item.fingerprint for item in prune_seen_events(events, retention_days=retention_days)}


def save_seen_events(path: Path, events: list[SeenEvent], retention_days: int = 3) -> None:
    payload = {"items": [item.to_dict() for item in prune_seen_events(events, retention_days=retention_days)]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

