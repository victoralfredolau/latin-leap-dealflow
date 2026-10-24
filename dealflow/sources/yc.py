"""Y Combinator vía el dataset público yc-oss (github.com/yc-oss/api)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Signal
from .base import SourceResult, get
from ..geo import country_from_text


def fetch_yc(cfg: dict, paises_tesis: list[str]) -> SourceResult:
    yc = cfg.get("yc") or {}
    r = SourceResult("Y Combinator")
    try:
        data = get(yc["url"], timeout=60).json()
    except Exception as e:  # noqa: BLE001
        r.fail(e)
        return r
    cutoff = datetime.now(timezone.utc) - timedelta(days=30 * yc.get("meses_recientes", 18))
    for c in data:
        if c.get("status") not in ("Active", None):
            continue
        launched = c.get("launched_at")
        ld = datetime.fromtimestamp(launched, tz=timezone.utc) if launched else None
        if ld and ld < cutoff:
            continue
        loc = c.get("all_locations") or ""
        country = country_from_text(loc)
        regions = c.get("regions") or []
        if country not in paises_tesis:
            continue
        if "Brazil" in regions:
            continue
        r.signals.append(Signal(
            source="Y Combinator", source_type="aceleradora",
            title=f"{c['name']} ({c.get('batch')}) — {c.get('one_liner') or ''}".strip(" —"),
            url=c.get("url") or "", published_at=ld.isoformat() if ld else None,
            summary=(c.get("long_description") or "")[:1200],
            company_hint=c.get("name"), website_hint=c.get("website"), country_hint=country,
            extra={"batch": c.get("batch"), "team_size": c.get("team_size"),
                   "industria": c.get("industry"), "tags": c.get("tags"), "ubicacion": loc,
                   "contratando": c.get("isHiring")},
        ))
    return r
