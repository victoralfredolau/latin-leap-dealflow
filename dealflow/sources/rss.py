"""Fuentes RSS: medios especializados y Google News."""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus

import feedparser

from ..models import Signal
from .base import SourceResult, get

_TAG = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", s or ""))).strip()


def _date(entry) -> datetime | None:
    for k in ("published_parsed", "updated_parsed"):
        t = entry.get(k)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def _parse(content: bytes, source: str, cutoff: datetime, source_type: str = "noticia") -> list[Signal]:
    feed = feedparser.parse(content)
    out = []
    for e in feed.entries:
        d = _date(e)
        if d and d < cutoff:
            continue
        title = _clean(e.get("title", ""))
        summary = _clean(e.get("summary", ""))[:2500]
        outlet = None
        if e.get("source") and isinstance(e.source, dict):
            outlet = e.source.get("title")
        # Google News agrega " - Medio" al título
        if source == "Google News" and " - " in title:
            title, _, outlet2 = title.rpartition(" - ")
            outlet = outlet or outlet2
        out.append(Signal(
            source=source, source_type=source_type, title=title, url=e.get("link", ""),
            published_at=d.isoformat() if d else None, summary=summary,
            extra={"medio": outlet} if outlet else {},
        ))
    return out


def fetch_feeds(cfg: dict, ventana_dias: int) -> list[SourceResult]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ventana_dias)
    results = []
    for f in cfg.get("rss", []):
        r = SourceResult(f["nombre"])
        try:
            r.signals = _parse(get(f["url"]).content, f["nombre"], cutoff)
        except Exception as e:  # noqa: BLE001
            r.fail(e)
        results.append(r)
    return results


def fetch_google_news(cfg: dict) -> SourceResult:
    gn = cfg.get("google_news") or {}
    dias = gn.get("dias", 14)
    cutoff = datetime.now(timezone.utc) - timedelta(days=dias)
    r = SourceResult("Google News")
    errors = []
    seen = set()
    for c in gn.get("consultas", []):
        hl = c.get("hl", gn.get("hl", "es-419"))
        gl = c.get("gl", "MX")
        q = f"{c['q']} when:{dias}d"
        url = (f"https://news.google.com/rss/search?q={quote_plus(q)}"
               f"&hl={hl}&gl={gl}&ceid={gl}:{hl.split('-')[0]}")
        try:
            for s in _parse(get(url).content, "Google News", cutoff):
                k = s.title.lower()
                if k in seen:
                    continue
                seen.add(k)
                s.extra["consulta"] = c["q"]
                r.signals.append(s)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{c['q']}: {e}")
    if errors and not r.signals:
        r.fail("; ".join(errors))
    elif errors:
        r.error = f"{len(errors)} consultas fallaron"
    return r
