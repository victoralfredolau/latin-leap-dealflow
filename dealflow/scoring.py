"""Score compuesto 0–100 contra la tesis de Latin Leap. Transparente y auditable: cada deal guarda
su desglose por componente para que el equipo entienda por qué quedó en A, B o C."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

SIGNAL_VALUE = {"aceleradora": 0.6, "noticia": 0.3, "contratacion": 0.4, "lanzamiento": 0.4}


def _parse(d: str | None) -> datetime | None:
    if not d:
        return None
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00"))
    except ValueError:
        return None


def score_deal(deal: dict, thesis: dict) -> dict:
    w = thesis["pesos"]
    paises = set(thesis["paises_tesis"])
    excl = set(thesis.get("paises_excluidos", []))

    pais = deal.get("pais")
    if pais in paises:
        geo = 1.0
    elif pais in excl or (pais and pais not in paises):
        geo = 0.0
    else:
        geo = 0.3  # país no identificado

    etapa = thesis["etapa_puntos"].get(deal.get("etapa") or "desconocida", 0.5)
    tec = {True: 1.0, False: 0.0}.get(deal.get("tecnologia"), 0.5)

    # Señal: tipo de evidencia + ronda anunciada + múltiples fuentes + recencia
    tipos = {s["tipo"] for s in deal.get("senales", [])}
    sen = max([SIGNAL_VALUE.get(t, 0.3) for t in tipos] or [0.3])
    if deal.get("monto_usd") or deal.get("inversionistas"):
        sen += 0.3
    if len({s["fuente"] for s in deal.get("senales", [])}) >= 2:
        sen += 0.2
    last = _parse(deal.get("ultima_senal"))
    if last and last >= datetime.now(timezone.utc) - timedelta(days=14):
        sen += 0.1
    sen = min(sen, 1.0)

    cal = (deal.get("calidad") or 5) / 10

    parts = {
        "geografia": round(w["geografia"] * geo, 1),
        "etapa": round(w["etapa"] * etapa, 1),
        "tecnologia": round(w["tecnologia"] * tec, 1),
        "senal": round(w["senal"] * sen, 1),
        "calidad": round(w["calidad"] * cal, 1),
    }
    total = round(sum(parts.values()))
    en_tesis = geo > 0 and deal.get("etapa") != "serie-b+" and deal.get("tecnologia") is not False
    if not en_tesis:
        prioridad = "Fuera de tesis"
    elif total >= thesis["prioridad"]["A"]:
        prioridad = "A"
    elif total >= thesis["prioridad"]["B"]:
        prioridad = "B"
    else:
        prioridad = "C"
    return {"score": total, "desglose": parts, "prioridad": prioridad, "en_tesis": en_tesis}
