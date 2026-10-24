"""Hacker News (API pública de Algolia): lanzamientos de founders LATAM."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from ..geo import country_from_text
from ..models import Signal
from .base import SourceResult, get

API = "https://hn.algolia.com/api/v1/search_by_date"


def fetch_hn(cfg: dict) -> SourceResult:
    hn = cfg.get("hackernews") or {}
    r = SourceResult("Hacker News")
    since = int(time.time()) - 86400 * hn.get("dias", 30)
    seen = set()
    errors = 0
    for term in hn.get("terminos", []):
        for tag in ("show_hn", "launch_hn"):
            try:
                js = get(API, params={"query": term, "tags": tag,
                                      "numericFilters": f"created_at_i>{since}", "hitsPerPage": 50}).json()
            except Exception:  # noqa: BLE001
                errors += 1
                continue
            for h in js.get("hits", []):
                if h["objectID"] in seen:
                    continue
                seen.add(h["objectID"])
                text = f"{h.get('title', '')} {h.get('story_text') or ''}"
                if not country_from_text(text):   # exige mención real de país/ciudad LATAM
                    continue
                r.signals.append(Signal(
                    source="Hacker News", source_type="lanzamiento", title=h.get("title", ""),
                    url=f"https://news.ycombinator.com/item?id={h['objectID']}",
                    published_at=datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc).isoformat(),
                    summary=(h.get("story_text") or "")[:1000], website_hint=h.get("url"),
                    extra={"puntos": h.get("points")},
                ))
    if errors and not r.signals:
        r.fail(f"{errors} consultas fallaron")
    return r
