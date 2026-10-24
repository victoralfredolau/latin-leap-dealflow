"""Extracción estructurada de cada señal: con Claude (preferente) o con reglas (respaldo).

El LLM convierte texto libre (una nota de prensa, un post) en campos comparables: empresa, país,
etapa, sector, monto, fundadores, una calificación cualitativa y un borrador de primer contacto.
Si no hay API key o la llamada falla, el motor sigue funcionando con reglas deterministas.
"""
from __future__ import annotations

import json
import logging
import os
import re

from .geo import country_from_text, normalize_country
from .models import Signal

log = logging.getLogger(__name__)

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
BATCH = 10
MAX_STARTUPS_POR_SENAL = 15
TEXT_CHARS = 2500   # suficiente para que quepa la lista de una cohorte cuando la fuente la incluye

ETAPAS = ["idea", "pre-seed", "seed", "serie-a", "serie-b+", "desconocida"]

SYSTEM = """Eres analista de Venture Capital en Latin Leap, un fondo de USD 20M que invierte en startups de
tecnología en etapa pre-seed y seed en América Latina hispanohablante (México, Centroamérica, Caribe
hispano, Colombia, Venezuela, Ecuador, Perú, Bolivia, Chile, Argentina, Uruguay y Paraguay). Brasil
está fuera de tesis.

Recibirás señales crudas (noticias, registros de aceleradoras, lanzamientos, vacantes). Para cada una,
extrae la información de la startup PROTAGONISTA. Si la señal nombra VARIAS startups concretas (una
generación o cohorte de aceleradora, ganadores de un concurso, un portafolio anunciado), devuelve UN objeto
POR STARTUP nombrada, todos con el mismo id de la señal, hasta un máximo de 15. Sólo startups cuyo nombre
aparece en el texto; nunca completes la lista con conocimiento propio. Reglas:
- No inventes datos. Si un campo no aparece en el texto, usa null (o "desconocida" en etapa).
- es_oportunidad = true sólo si el objeto describe UNA startup concreta e identificable que podría ser
  un deal de VC. Es false para notas genéricas del ecosistema, reportes, eventos, rankings, fondos de
  inversión, corporativos grandes o empresas públicas.
- etapa: "idea", "pre-seed", "seed", "serie-a", "serie-b+" o "desconocida". Una ronda < USD 3M sin
  etiqueta suele ser pre-seed/seed; un batch de aceleradora sin ronda reportada es "pre-seed".
- monto_usd: monto de la ronda en USD (convierte si es obvio; si no, null).
- tecnologia: true si el producto es de base tecnológica (software, fintech, marketplace digital, IA,
  hardware, biotech, etc.).
- calidad: 0–10, tu juicio de qué tan atractiva es para un fondo pre-seed/seed, basado SÓLO en la
  evidencia (inversionistas reconocidos, aceleradora top, tracción mencionada, mercado grande,
  diferenciación). 5 = neutral/sin evidencia.
- razon: una frase en español que justifique la calificación.
- resumen: 1–2 frases en español de qué hace la startup.
- mensaje: borrador breve (3–4 frases, español, tono cálido y profesional) de primer contacto del
  equipo de Latin Leap a los founders, mencionando algo específico de la señal. Sin promesas de inversión.

Responde EXCLUSIVAMENTE con un arreglo JSON (al menos un objeto por señal; varios si la señal nombra
varias startups), con las llaves:
id, es_oportunidad, empresa, sitio_web, pais, ciudad, sector, etapa, monto_usd, inversionistas,
fundadores, tecnologia, calidad, razon, resumen, mensaje."""


def _payload(s: Signal) -> dict:
    d = {"id": s.id, "fuente": s.source, "tipo": s.source_type, "titulo": s.title,
         "texto": s.summary[:TEXT_CHARS], "url": s.url}
    for k, v in (("empresa_sugerida", s.company_hint), ("web_sugerida", s.website_hint),
                 ("pais_sugerido", s.country_hint)):
        if v:
            d[k] = v
    if s.extra:
        d["datos"] = {k: v for k, v in s.extra.items() if v not in (None, "", [])}
    return d


def _parse_json_array(text: str) -> list[dict]:
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("sin JSON en la respuesta")
    return json.loads(m.group(0))


def _clean(rec: dict, s: Signal, motor: str) -> dict:
    etapa = (rec.get("etapa") or "desconocida").lower().replace(" ", "-")
    etapa = {"pre-semilla": "pre-seed", "semilla": "seed", "series-a": "serie-a", "serie-b": "serie-b+",
             "series-b": "serie-b+", "serie-c": "serie-b+", "growth": "serie-b+"}.get(etapa, etapa)
    if etapa not in ETAPAS:
        etapa = "desconocida"
    try:
        calidad = max(0.0, min(10.0, float(rec.get("calidad") if rec.get("calidad") is not None else 5)))
    except (TypeError, ValueError):
        calidad = 5.0
    monto = rec.get("monto_usd")
    try:
        monto = float(monto) if monto not in (None, "") else None
    except (TypeError, ValueError):
        monto = None

    def _lst(v):
        if not v:
            return []
        return [str(x) for x in v] if isinstance(v, list) else [str(v)]

    return {
        "es_oportunidad": bool(rec.get("es_oportunidad")),
        "empresa": (rec.get("empresa") or s.company_hint or None),
        "sitio_web": rec.get("sitio_web") or s.website_hint,
        "pais": normalize_country(rec.get("pais")) or s.country_hint,
        "ciudad": rec.get("ciudad"),
        "sector": rec.get("sector"),
        "etapa": etapa,
        "monto_usd": monto,
        "inversionistas": _lst(rec.get("inversionistas")),
        "fundadores": _lst(rec.get("fundadores")),
        "tecnologia": rec.get("tecnologia"),
        "calidad": calidad,
        "razon": rec.get("razon"),
        "resumen": rec.get("resumen"),
        "mensaje": rec.get("mensaje"),
        "motor": motor,
    }


# ---------------------------------------------------------------- LLM
def extract_llm(signals: list[Signal]) -> dict[str, list[dict]]:
    """Devuelve id de señal → lista de extracciones (una por startup nombrada en la señal)."""
    import anthropic  # import diferido: el respaldo por reglas no lo necesita

    client = anthropic.Anthropic()
    out: dict[str, list[dict]] = {}
    for i in range(0, len(signals), BATCH):
        chunk = signals[i:i + BATCH]
        msg = "Señales:\n" + json.dumps([_payload(s) for s in chunk], ensure_ascii=False)
        try:
            resp = client.messages.create(model=MODEL, max_tokens=16000, system=SYSTEM,
                                          messages=[{"role": "user", "content": msg}])
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            recs: dict[str, list[dict]] = {}
            for r in _parse_json_array(text):
                if isinstance(r, dict) and r.get("id"):
                    recs.setdefault(r["id"], []).append(r)
        except Exception as e:  # noqa: BLE001
            log.warning("LLM falló en lote %s: %s — uso reglas", i // BATCH, e)
            recs = {}
        for s in chunk:
            if s.id not in recs:
                out[s.id] = [extract_rules(s)]
                continue
            lst = recs[s.id][:MAX_STARTUPS_POR_SENAL]
            # en notas multi-startup, el nombre/web/país sugeridos por la fuente no aplican a todas
            multi = len(lst) > 1
            base = Signal(**{**s.to_dict(), "company_hint": None, "website_hint": None, "country_hint": None}) if multi else s
            out[s.id] = [_clean(r, base, "llm") for r in lst]
    return out


# ---------------------------------------------------------------- Reglas
_FUND = r"(levanta|levantó|recauda|recaudó|cierra|cerró|obtiene|obtuvo|asegura|aseguró|consigue|consiguió|capta|captó|anuncia ronda|raises|raised|secures|secured|closes|closed|lands|landed|bags|nabs)"
_NAME_RE = re.compile(
    r"^(?:la |el )?(?:(?:startup|fintech|proptech|healthtech|edtech|insurtech|agtech|legaltech|insurtech|plataforma|empresa)"
    r"(?: [a-záéíóúñ]+)?(?: de [a-záéíóúñ ]+?)? )?"
    r"([A-Z0-9][\w\.\-&']*(?: [A-Z0-9][\w\.\-&']*){0,3}),? " + _FUND, re.I)
_STAGE = [("pre-seed", r"pre[\s\-]?seed|pre[\s\-]?semilla|presemilla"), ("seed", r"\bseed\b|semilla"),
          ("serie-a", r"serie[s]? a\b"), ("serie-b+", r"serie[s]? [b-f]\b|growth round")]
_AMT = re.compile(r"(?:US\$|USD|\$)\s?(\d+(?:[.,]\d+)?)\s?(millones|mdd|m\b|million|mil|k\b)?", re.I)
_TECH = re.compile(r"\b(app|plataforma|software|saas|fintech|ia\b|ai\b|inteligencia artificial|marketplace|"
                   r"api|digital|tech|tecnolog|blockchain|cripto|data|datos|cloud|nube|insurtech|healthtech|"
                   r"edtech|proptech|agtech|logtech|biotech|deeptech|robot|e-?commerce|b2b)", re.I)
_PREFIX = re.compile(r"^(?:(?:argentine|argentinian|colombian|mexican|chilean|peruvian|uruguayan|ecuadorian|"
                     r"panamanian|guatemalan|costa rican|dominican|paraguayan|bolivian|venezuelan|brazilian|"
                     r"latin american|latam|fintech|proptech|healthtech|edtech|insurtech|agtech|biotech|legaltech|"
                     r"climatech|ai|startup|company|platform)\s+)+", re.I)
_NOISE = re.compile(r"\b(ranking|reporte|informe|estudio|evento|foro|summit|convocatoria|webinar|tendencias|"
                    r"fondo de|vc fund|lanza fondo|ecosistema)\b", re.I)


def extract_rules(s: Signal) -> dict:
    text = f"{s.title}. {s.summary}"
    name = s.company_hint
    if not name:
        m = _NAME_RE.search(s.title)
        if m:
            name = _PREFIX.sub("", m.group(1).strip(" ,.:")).strip() or None
    etapa = "desconocida"
    for st, pat in _STAGE:
        if re.search(pat, text, re.I):
            etapa = st
            break
    if etapa == "desconocida" and s.source_type == "aceleradora":
        etapa = "pre-seed"
    monto = None
    m = _AMT.search(text)
    if m:
        try:
            v = float(m.group(1).replace(",", "."))
            unit = (m.group(2) or "").lower()
            monto = v * 1e6 if unit in ("millones", "mdd", "m", "million") else v * 1e3 if unit in ("mil", "k") else v
        except ValueError:
            pass
    if etapa == "desconocida" and monto:
        etapa = "seed" if monto <= 3e6 else "serie-a" if monto <= 15e6 else "serie-b+"
    funding = bool(re.search(_FUND, s.title, re.I))
    es_op = bool(name) and not _NOISE.search(s.title) and (
        funding or s.source_type in ("aceleradora", "contratacion", "lanzamiento"))
    return {
        "es_oportunidad": es_op, "empresa": name, "sitio_web": s.website_hint,
        "pais": s.country_hint or country_from_text(text), "ciudad": None,
        "sector": (s.extra or {}).get("industria"), "etapa": etapa, "monto_usd": monto,
        "inversionistas": [], "fundadores": [], "tecnologia": True if (_TECH.search(text) or s.source_type == "aceleradora") else None,
        "calidad": 6.5 if s.source_type == "aceleradora" else 5.0,
        "razon": "Clasificado por reglas (sin LLM): calidad neutral salvo aceleradora reconocida.",
        "resumen": (s.summary or s.title)[:240], "mensaje": None, "motor": "reglas",
    }


def extract(signals: list[Signal]) -> dict[str, list[dict]]:
    if not signals:
        return {}
    if os.getenv("ANTHROPIC_API_KEY"):
        return extract_llm(signals)
    log.info("ANTHROPIC_API_KEY no configurada: extracción por reglas")
    return {s.id: [extract_rules(s)] for s in signals}
