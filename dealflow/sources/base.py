"""Utilidades HTTP compartidas por las fuentes."""
from __future__ import annotations

import time

import requests

UA = "LatinLeapDealflowBot/1.0 (+https://github.com; sourcing de startups early-stage)"
_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "es-419,es;q=0.9,en;q=0.6"})


def get(url: str, *, params: dict | None = None, timeout: int = 25, retries: int = 2) -> requests.Response:
    last = None
    for i in range(retries + 1):
        try:
            r = _session.get(url, params=params, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504) and i < retries:
                time.sleep(2 * (i + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # noqa: PERF203
            last = e
            if i < retries:
                time.sleep(2 * (i + 1))
    raise last  # type: ignore[misc]


class SourceResult:
    """Señales + estado de salud de la fuente (se muestra en el tablero)."""

    def __init__(self, name: str):
        self.name = name
        self.signals = []
        self.ok = True
        self.error: str | None = None
        self.fetched = 0

    def fail(self, err: Exception | str):
        self.ok = False
        self.error = str(err)[:300]

    def health(self) -> dict:
        return {"fuente": self.name, "ok": self.ok, "senales": len(self.signals), "error": self.error}
