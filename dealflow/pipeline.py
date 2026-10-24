"""Orquestador: captura → pre-filtro → extracción → deduplicación → scoring → métricas → tablero."""
from __future__ import annotations

import csv
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from .extract import extract
from .geo import countries_in
from .models import Signal, company_key, domain_of, now_iso
from .scoring import score_deal

log = logging.getLogger("dealflow")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
_FUND_HINT = re.compile(r"levant|recaud|ronda|semilla|seed|raise|secur|closes|inversi|acelerad|aceleraci|incubad|batch|cohort|"
                        r"generaci|seleccion|ganador|winner|demo day|lanza|launch",
                        re.I)


# ------------------------------------------------------------------ persistencia
def _load(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def _save(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")


def load_config():
    thesis = yaml.safe_load((ROOT / "config/thesis.yaml").read_text(encoding="utf-8"))
    sources = yaml.safe_load((ROOT / "config/sources.yaml").read_text(encoding="utf-8"))
    return thesis, sources


def load_known() -> dict[str, str]:
    """Empresas que Latin Leap ya conoce (export del CRM y/o portafolio público).

    Devuelve llave canónica → etiqueta de origen ("Portafolio Latin Leap", "Pipeline CRM", …). Estas empresas se
    muestran con su etiqueta y NO suman a la meta de +10 %, para que la métrica sea estrictamente incremental.
    Columnas del CSV: empresa, sitio_web, fuente (fuente vacía = "Pipeline CRM").
    """
    p = DATA / "pipeline_existente.csv"
    keys: dict[str, str] = {}
    if p.exists():
        with p.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                label = (row.get("fuente") or "").strip() or "Pipeline CRM"
                for k in (company_key(row.get("empresa")), company_key(None, row.get("sitio_web"))):
                    if k:
                        keys[k] = label
    return keys


def known_label(d: dict, known: dict[str, str]) -> str | None:
    for k in (d.get("key"), company_key(d.get("empresa")), company_key(None, d.get("sitio_web"))):
        if k and k in known:
            return known[k]
    return None


# ------------------------------------------------------------------ captura
def collect(thesis: dict, sources: dict, only: set[str] | None = None):
    from .sources.getonbrd import fetch_getonbrd
    from .sources.hackernews import fetch_hn
    from .sources.rss import fetch_feeds, fetch_google_news
    from .sources.yc import fetch_yc

    paises = thesis["paises_tesis"]
    jobs = {
        "rss": lambda: fetch_feeds(sources, thesis["ventana_dias"]),
        "google_news": lambda: [fetch_google_news(sources)],
        "yc": lambda: [fetch_yc(sources, paises)],
        "hackernews": lambda: [fetch_hn(sources)],
        "getonbrd": lambda: [fetch_getonbrd(sources, paises)],
    }
    results = []
    for name, fn in jobs.items():
        if only and name not in only:
            continue
        try:
            results.extend(fn())
        except Exception as e:  # noqa: BLE001 — una fuente caída nunca detiene la corrida
            from .sources.base import SourceResult
            r = SourceResult(name)
            r.fail(e)
            results.append(r)
    return results


def prefilter(signals: list[Signal], thesis: dict) -> tuple[list[Signal], int]:
    """Descarta lo obvio antes de gastar LLM: sólo-Brasil y notas sin indicio de startup/ronda."""
    keep, dropped = [], 0
    excl = set(thesis.get("paises_excluidos", []))
    for s in signals:
        text = f"{s.title} {s.summary}"
        cs = set(countries_in(text)) | ({s.country_hint} if s.country_hint else set())
        if cs and cs <= excl:
            dropped += 1
            continue
        if s.source_type == "noticia" and not _FUND_HINT.search(text):
            dropped += 1
            continue
        keep.append(s)
    order = {"aceleradora": 0, "contratacion": 1, "noticia": 2, "lanzamiento": 3}
    keep.sort(key=lambda s: (order.get(s.source_type, 9), -(len(s.summary))))
    return keep, dropped


# ------------------------------------------------------------------ merge
_FIELDS = ["empresa", "sitio_web", "pais", "ciudad", "sector", "etapa", "monto_usd", "tecnologia",
           "resumen", "mensaje", "razon"]


def merge(deals: dict, s: Signal, ex: dict, known: dict[str, str]) -> tuple[str | None, bool]:
    if not ex.get("es_oportunidad") or not ex.get("empresa"):
        return None, False
    k_dom = company_key(None, ex.get("sitio_web"))
    k_name = company_key(ex["empresa"])
    key = next((k for k in (k_dom, k_name) if k and k in deals), None) or k_dom or k_name
    if not key:
        return None, False
    # alias: si existe por nombre y ahora tenemos dominio, conserva la llave existente
    if k_name and k_name in deals:
        key = k_name
    is_new = key not in deals
    d = deals.setdefault(key, {"key": key, "primera_vista": now_iso(), "senales": [], "inversionistas": [],
                                "fundadores": [], "calidad": None, "motor": ex.get("motor")})
    for f in _FIELDS:
        v = ex.get(f)
        if v in (None, "", []) or (f == "etapa" and v == "desconocida" and d.get("etapa")):
            continue
        if f in ("resumen", "mensaje", "razon") and d.get(f) and ex.get("motor") != "llm":
            continue
        d[f] = v
    if d.get("sitio_web") and not domain_of(d["sitio_web"]):
        d["sitio_web"] = None
    d["inversionistas"] = sorted(set(d["inversionistas"]) | set(ex.get("inversionistas") or []))
    d["fundadores"] = sorted(set(d["fundadores"]) | set(ex.get("fundadores") or []))
    d["calidad"] = max(filter(lambda x: x is not None, [d.get("calidad"), ex.get("calidad")]), default=5)
    if ex.get("motor") == "llm":
        d["motor"] = "llm"
    if not any(x["url"] == s.url for x in d["senales"]):
        d["senales"].append({"fuente": s.source, "tipo": s.source_type, "titulo": s.title, "url": s.url,
                             "fecha": s.published_at, "medio": (s.extra or {}).get("medio")})
    fechas = sorted(filter(None, (x.get("fecha") for x in d["senales"])))
    d["fecha_evidencia"] = fechas[0] if fechas else d["primera_vista"]
    d["ultima_senal"] = fechas[-1] if fechas else d["primera_vista"]
    d["conocido_fuente"] = known_label(d, known)
    d["conocido"] = bool(d["conocido_fuente"])
    return key, is_new


# ------------------------------------------------------------------ métricas
def metrics(deals: dict, thesis: dict, runs: list[dict]) -> dict:
    meta = round(thesis["fondo"]["baseline_deals_mes"] * thesis["fondo"]["meta_incremento"])
    now = datetime.now(timezone.utc)

    def _dt(x):
        try:
            return datetime.fromisoformat(x.replace("Z", "+00:00"))
        except (AttributeError, ValueError):
            return None

    calif = [d for d in deals.values() if d.get("prioridad") in ("A", "B") and not d.get("conocido")]
    c30 = [d for d in calif if (_dt(d.get("fecha_evidencia")) or now) >= now - timedelta(days=30)]
    by_week: dict[str, int] = {}
    for d in calif:
        dt = _dt(d.get("fecha_evidencia"))
        if dt:
            wk = (dt - timedelta(days=dt.weekday())).date().isoformat()
            by_week[wk] = by_week.get(wk, 0) + 1
    by_src: dict[str, int] = {}
    for d in calif:
        for f in {s["fuente"] for s in d["senales"]}:
            by_src[f] = by_src.get(f, 0) + 1
    by_country: dict[str, int] = {}
    for d in calif:
        by_country[d.get("pais") or "?"] = by_country.get(d.get("pais") or "?", 0) + 1
    return {
        "actualizado": now_iso(),
        "baseline_mes": thesis["fondo"]["baseline_deals_mes"],
        "meta_incremental_mes": meta,
        "calificados_30d": len(c30),
        "prioridad_a_30d": sum(1 for d in c30 if d["prioridad"] == "A"),
        "incremento_vs_baseline": round(len(c30) / thesis["fondo"]["baseline_deals_mes"], 3),
        "cumplimiento_meta": round(len(c30) / meta, 2) if meta else None,
        "total_deals": len(deals),
        "total_calificados": len(calif),
        "conocidos_detectados": sum(1 for d in deals.values() if d.get("conocido")),
        "por_semana": dict(sorted(by_week.items())[-12:]),
        "por_fuente": dict(sorted(by_src.items(), key=lambda x: -x[1])),
        "por_pais": dict(sorted(by_country.items(), key=lambda x: -x[1])),
        "corridas": runs[-30:],
    }


# ------------------------------------------------------------------ main
def run(only: set[str] | None = None, fixtures: Path | None = None, rescore_only: bool = False) -> dict:
    thesis, sources = load_config()
    deals = _load(DATA / "deals.json", {})
    seen = _load(DATA / "senales_procesadas.json", {})
    runs = _load(DATA / "corridas.json", [])
    known = load_known()
    started = now_iso()

    health, new_keys, n_raw, n_drop, n_proc = [], [], 0, 0, 0
    if not rescore_only:
        if fixtures:
            raw = [Signal(**x) for x in json.loads(fixtures.read_text(encoding="utf-8"))]
            health = [{"fuente": "fixtures", "ok": True, "senales": len(raw), "error": None}]
        else:
            results = collect(thesis, sources, only)
            raw = [s for r in results for s in r.signals]
            health = [r.health() for r in results]
        n_raw = len(raw)
        fresh = [s for s in {s.id: s for s in raw}.values() if s.id not in seen]
        cand, n_drop = prefilter(fresh, thesis)
        cap = thesis.get("max_senales_llm_por_corrida", 200)
        batch, rest = cand[:cap], cand[cap:]
        exs = extract(batch)
        for s in batch:
            keys = []
            for e in exs[s.id]:
                key, is_new = merge(deals, s, e, known)
                if key:
                    keys.append(key)
                if is_new:
                    new_keys.append(key)
            seen[s.id] = {"fecha": started, "deals": sorted(set(keys))}
        n_proc = len(batch)
        log.info("Pendientes para la siguiente corrida por límite de costo: %d", len(rest))

    for d in deals.values():
        d.update(score_deal(d, thesis))
        d["conocido_fuente"] = known_label(d, known)
        d["conocido"] = bool(d["conocido_fuente"])

    nuevos_calif = [k for k in new_keys if deals[k]["prioridad"] in ("A", "B") and not deals[k]["conocido"]]
    run_rec = {"inicio": started, "fin": now_iso(), "senales_crudas": n_raw, "descartadas_prefiltro": n_drop,
               "procesadas": n_proc, "deals_nuevos": len(new_keys), "calificados_nuevos": len(nuevos_calif),
               "motor": "llm" if os.getenv("ANTHROPIC_API_KEY") else "reglas", "fuentes": health}
    if not rescore_only:
        runs.append(run_rec)
    m = metrics(deals, thesis, runs)

    _save(DATA / "deals.json", deals)
    _save(DATA / "senales_procesadas.json", seen)
    _save(DATA / "corridas.json", runs)
    _save(DATA / "metricas.json", m)

    from .site import build_site
    build_site(deals, m, thesis)
    return run_rec
