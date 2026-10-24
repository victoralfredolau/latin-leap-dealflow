"""Modelos de datos y utilidades de normalización."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_SUFFIXES = r"\b(inc|llc|ltd|s\.?a\.?(p\.?i\.?)?( de c\.?v\.?)?|sas|spa|corp|co|labs?|app|ai|hq|io)\b\.?"


def company_key(name: str | None, website: str | None = None) -> str | None:
    """Llave canónica de deduplicación: dominio si existe; si no, nombre normalizado."""
    dom = domain_of(website)
    if dom:
        return "d:" + dom
    if not name:
        return None
    n = strip_accents(name).lower()
    n = re.sub(_SUFFIXES, " ", n)
    n = re.sub(r"[^a-z0-9]+", "", n)
    return ("n:" + n) if len(n) >= 2 else None


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    u = url if "://" in url else "https://" + url
    try:
        host = (urlparse(u).hostname or "").lower()
    except ValueError:
        return None
    host = re.sub(r"^www\d?\.", "", host)
    # Dominios que NO identifican a una compañía (agregadores, redes, medios)
    generic = (
        "news.google.com", "google.com", "linkedin.com", "twitter.com", "x.com", "facebook.com",
        "instagram.com", "youtube.com", "medium.com", "github.com", "ycombinator.com",
        "news.ycombinator.com", "getonbrd.com", "techcrunch.com", "latamlist.com", "contxto.com",
        "startupeable.com", "pulsosocial.com", "apps.apple.com", "play.google.com", "notion.site",
    )
    if not host or "." not in host or any(host == g or host.endswith("." + g) for g in generic):
        return None
    return host


def sid(*parts: str) -> str:
    return hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:16]


@dataclass
class Signal:
    """Una señal cruda: una noticia, un registro de YC, un post de HN, una vacante."""
    source: str                 # p. ej. "Google News", "YC", "LatamList"
    source_type: str            # noticia | aceleradora | lanzamiento | contratacion
    title: str
    url: str
    published_at: str | None = None
    summary: str = ""
    company_hint: str | None = None
    website_hint: str | None = None
    country_hint: str | None = None
    extra: dict = field(default_factory=dict)
    id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = sid(self.source, self.url or self.title)

    def to_dict(self) -> dict:
        return asdict(self)
