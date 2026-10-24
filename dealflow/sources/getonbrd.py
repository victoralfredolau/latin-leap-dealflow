"""Get on Board: startups LATAM contratando perfiles tech (API pública v0, sin autenticación).

Nota: el esquema exacto del JSON se valida en la primera corrida en GitHub Actions; el parser es
defensivo y, si la API cambia, la fuente se marca como caída en el tablero sin romper el motor.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ..geo import normalize_country
from ..models import Signal
from .base import SourceResult, get

BASE = "https://www.getonbrd.com/api/v0"


def _attr(obj, *path):
    for p in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(p)
    return obj


def fetch_getonbrd(cfg: dict, paises_tesis: list[str]) -> SourceResult:
    g = cfg.get("getonbrd") or {}
    r = SourceResult("Get on Board")
    cutoff = datetime.now(timezone.utc) - timedelta(days=g.get("dias", 21))
    by_company: dict[str, dict] = defaultdict(lambda: {"jobs": []})
    errors = []
    for cat in g.get("categorias", []):
        try:
            js = get(f"{BASE}/categories/{cat}/jobs",
                     params={"per_page": g.get("por_pagina", 100), "page": 1, "expand": '["company"]'}).json()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{cat}: {e}")
            continue
        for job in js.get("data", []):
            a = job.get("attributes", {})
            ts = a.get("published_at")
            pub = datetime.fromtimestamp(ts, tz=timezone.utc) if isinstance(ts, (int, float)) else None
            if pub and pub < cutoff:
                continue
            comp = _attr(a, "company", "data") or {}
            ca = comp.get("attributes", {}) if isinstance(comp, dict) else {}
            name = ca.get("name")
            if not name:
                continue
            country = normalize_country(ca.get("country") or a.get("country"))
            if country not in paises_tesis:
                continue
            emp = ca.get("employees") or ca.get("size")
            try:
                if emp and int(str(emp).split("-")[0].strip("+ ")) > g.get("max_empleados", 50):
                    continue
            except ValueError:
                pass
            c = by_company[name]
            c.update(name=name, web=ca.get("web") or ca.get("website"), country=country,
                     desc=(ca.get("description") or ca.get("long_description") or "")[:900],
                     pub=max(filter(None, [c.get("pub"), pub]), default=None),
                     url=job.get("links", {}).get("public_url") or a.get("public_url") or "")
            c["jobs"].append(a.get("title"))
    for name, c in by_company.items():
        r.signals.append(Signal(
            source="Get on Board", source_type="contratacion",
            title=f"{name} está contratando: {', '.join(filter(None, c['jobs']))[:160]}",
            url=c.get("url") or "https://www.getonbrd.com", published_at=c["pub"].isoformat() if c.get("pub") else None,
            summary=c.get("desc", ""), company_hint=name, website_hint=c.get("web"), country_hint=c.get("country"),
            extra={"vacantes": len(c["jobs"])},
        ))
    if errors and not r.signals:
        r.fail("; ".join(errors)[:300])
    return r
