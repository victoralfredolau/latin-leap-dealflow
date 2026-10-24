"""Pruebas del motor. Correr con: python -m pytest -q"""
import json
import sys
import types
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dealflow import extract as ex  # noqa: E402
from dealflow.geo import country_from_text, normalize_country  # noqa: E402
from dealflow.models import Signal, company_key  # noqa: E402
from dealflow.pipeline import merge, prefilter  # noqa: E402
from dealflow.scoring import score_deal  # noqa: E402

THESIS = yaml.safe_load((ROOT / "config/thesis.yaml").read_text(encoding="utf-8"))


def sig(title, summary="", **kw):
    return Signal(source=kw.pop("source", "LatamList"), source_type=kw.pop("source_type", "noticia"),
                  title=title, url=kw.pop("url", "https://x.com/" + title[:10]), summary=summary, **kw)


def test_geo():
    assert country_from_text("Colombian fintech Fronte") == "Colombia"
    assert country_from_text("startup regiomontana de Monterrey") == "México"
    assert country_from_text("Bogotá, Colombia; Remote") == "Colombia"
    assert normalize_country("MX") == "México"
    assert normalize_country("Peru") == "Perú"


def test_company_key_dedup():
    assert company_key("Dapta Inc.") == company_key("dapta")
    assert company_key("X", "https://www.dapta.ai/es") == "d:dapta.ai"
    assert company_key("X", "https://news.google.com/rss/articles/abc") == company_key("X")


def test_rules_extraction():
    r = ex.extract_rules(sig("Colombian fintech Fronte raises pre-seed round led by Rally Cap VC"))
    assert r["empresa"] == "Fronte" and r["pais"] == "Colombia" and r["etapa"] == "pre-seed" and r["es_oportunidad"]
    r = ex.extract_rules(sig("Startup mexicana Kueski levanta US$ 2 millones en ronda semilla"))
    assert r["pais"] == "México" and r["etapa"] == "seed" and r["monto_usd"] == 2e6
    r = ex.extract_rules(sig("Ranking: las 10 startups más innovadoras de Chile"))
    assert not r["es_oportunidad"]


def test_prefilter_drops_brazil_only():
    keep, dropped = prefilter([sig("Brazilian startup Imersa raises $50K", "São Paulo"),
                               sig("Chilean startup Foo raises seed")], THESIS)
    assert dropped == 1 and keep[0].title.startswith("Chilean")


def test_scoring_thesis_rules():
    base = {"pais": "México", "etapa": "pre-seed", "tecnologia": True, "calidad": 8,
            "senales": [{"fuente": "YC", "tipo": "aceleradora"}], "monto_usd": 5e5}
    s = score_deal(base, THESIS)
    assert s["prioridad"] == "A" and s["en_tesis"]
    assert score_deal({**base, "pais": "Brasil"}, THESIS)["prioridad"] == "Fuera de tesis"
    assert score_deal({**base, "etapa": "serie-b+"}, THESIS)["prioridad"] == "Fuera de tesis"
    assert sum(score_deal(base, THESIS)["desglose"].values()) <= 100


def test_merge_dedups_across_sources():
    deals = {}
    e1 = ex.extract_rules(sig("Dapta raises $6M seed round", "Colombian AI startup Dapta", url="https://a"))
    e2 = ex.extract_rules(sig("Startup colombiana Dapta levanta US$6 millones", url="https://b", source="Google News"))
    k1, n1 = merge(deals, sig("t1", url="https://a"), e1, set())
    k2, n2 = merge(deals, sig("t2", url="https://b", source="Google News"), e2, set())
    assert k1 == k2 and n1 and not n2 and len(deals[k1]["senales"]) == 2


def test_llm_path_with_mock(monkeypatch):
    s1 = sig("Dapta raises $6M seed round led by Chingona Ventures", "Colombian AI startup Dapta")
    s2 = sig("Mexico Tech Week: un espacio para la innovación")
    reply = json.dumps([
        {"id": s1.id, "es_oportunidad": True, "empresa": "Dapta", "sitio_web": "dapta.ai", "pais": "Colombia",
         "ciudad": None, "sector": "IA", "etapa": "seed", "monto_usd": 6000000, "inversionistas": ["Chingona Ventures"],
         "fundadores": [], "tecnologia": True, "calidad": 8, "razon": "Ronda liderada por fondo institucional",
         "resumen": "Plataforma de agentes de IA.", "mensaje": "Hola equipo de Dapta…"},
        {"id": s2.id, "es_oportunidad": False, "empresa": None, "etapa": "desconocida", "calidad": 0},
    ])

    class FakeMsgs:
        def create(self, **kw):
            assert "Latin Leap" in kw["system"]
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="```json\n" + reply + "\n```")])

    fake = types.SimpleNamespace(Anthropic=lambda: types.SimpleNamespace(messages=FakeMsgs()))
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    out = ex.extract_llm([s1, s2])
    assert len(out[s1.id]) == 1
    d1 = out[s1.id][0]
    assert d1["motor"] == "llm" and d1["inversionistas"] == ["Chingona Ventures"]
    assert d1["calidad"] == 8 and not out[s2.id][0]["es_oportunidad"]


def test_llm_failure_falls_back_to_rules(monkeypatch):
    class Boom:
        def create(self, **kw):
            raise RuntimeError("rate limit")

    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda: types.SimpleNamespace(messages=Boom())))
    s = sig("Colombian fintech Fronte raises pre-seed round")
    assert ex.extract_llm([s])[s.id][0]["motor"] == "reglas"


def test_known_portfolio_excluded_from_goal():
    from dealflow.pipeline import known_label, load_known, metrics
    known = load_known()
    assert known_label({"key": "n:dapta", "empresa": "Dapta"}, known) == "Portafolio Latin Leap"
    assert known_label({"key": "n:fronte", "empresa": "Fronte"}, known) is None
    deals = {"n:dapta": {"key": "n:dapta", "prioridad": "A", "conocido": True, "senales": [], "fecha_evidencia": None},
             "n:fronte": {"key": "n:fronte", "prioridad": "A", "conocido": False, "senales": [], "fecha_evidencia": None}}
    m = metrics(deals, THESIS, [])
    assert m["total_calificados"] == 1 and m["conocidos_detectados"] == 1


def test_cohort_note_yields_one_deal_per_startup(monkeypatch):
    """Una nota de generación de aceleradora con 3 startups nombradas → 3 deals con la misma evidencia."""
    s = sig("Start-Up Chile anuncia su nueva generación: Alfa, Beta y Gama entre las seleccionadas",
            "Alfa (fintech, Santiago), Beta (agtech, Lima) y Gama (IA, Bogotá) recibirán financiamiento sin equity.",
            source="Google News")
    rec = lambda n, pais: {"id": s.id, "es_oportunidad": True, "empresa": n, "pais": pais, "etapa": "pre-seed",
                           "tecnologia": True, "calidad": 7, "resumen": f"{n} startup", "razon": "Aceleradora pública"}
    reply = json.dumps([rec("Alfa", "Chile"), rec("Beta", "Perú"), rec("Gama", "Colombia")])

    class Msgs:
        def create(self, **kw):
            assert "VARIAS startups" in kw["system"]
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=reply)])

    monkeypatch.setitem(sys.modules, "anthropic",
                        types.SimpleNamespace(Anthropic=lambda: types.SimpleNamespace(messages=Msgs())))
    out = ex.extract_llm([s])
    assert [e["empresa"] for e in out[s.id]] == ["Alfa", "Beta", "Gama"]
    assert [e["pais"] for e in out[s.id]] == ["Chile", "Perú", "Colombia"]
    deals = {}
    keys = [merge(deals, s, e, {})[0] for e in out[s.id]]
    assert len(set(keys)) == 3
    assert all(deals[k]["senales"][0]["url"] == s.url for k in keys)
    for k in keys:
        assert score_deal(deals[k], THESIS)["prioridad"] in ("A", "B")


def test_prefilter_keeps_cohort_and_winner_notes():
    keep, dropped = prefilter([sig("CORFO anuncia las startups seleccionadas de su nueva generación"),
                               sig("iNNpulsa revela los ganadores de su convocatoria"),
                               sig("Mexico Tech Week: un espacio para la innovación")], THESIS)
    assert len(keep) == 2 and dropped == 1
