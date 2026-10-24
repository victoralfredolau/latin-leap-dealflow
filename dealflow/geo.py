"""Detección de país a partir de texto (nombres, gentilicios y ciudades, ES/EN)."""
from __future__ import annotations

import re

from .models import strip_accents

# país canónico → términos (sin acentos, minúsculas). Orden = prioridad de match.
_TERMS: dict[str, list[str]] = {
    "México": ["mexico", "mexicana", "mexicano", "mexican", "cdmx", "ciudad de mexico", "mexico city",
               "monterrey", "guadalajara", "nuevo leon", "jalisco", "queretaro", "puebla", "tijuana", "merida"],
    "Colombia": ["colombia", "colombiana", "colombiano", "colombian", "bogota", "medellin", "cali", "barranquilla"],
    "Chile": ["chile", "chilena", "chileno", "chilean", "santiago de chile", "valparaiso"],
    "Argentina": ["argentina", "argentino", "argentine", "buenos aires", "cordoba, argentina", "rosario", "mendoza"],
    "Perú": ["peru", "peruana", "peruano", "peruvian", "lima, peru", "arequipa"],
    "Uruguay": ["uruguay", "uruguaya", "uruguayo", "uruguayan", "montevideo"],
    "Ecuador": ["ecuador", "ecuatoriana", "ecuatoriano", "ecuadorian", "quito", "guayaquil"],
    "Costa Rica": ["costa rica", "costarricense", "costa rican", "san jose, costa rica"],
    "Guatemala": ["guatemala", "guatemalteca", "guatemalteco", "guatemalan"],
    "Panamá": ["panama", "panamena", "panameno", "panamanian"],
    "República Dominicana": ["republica dominicana", "dominicana", "dominican republic", "santo domingo"],
    "El Salvador": ["el salvador", "salvadorena", "salvadoreno", "salvadoran", "san salvador"],
    "Honduras": ["honduras", "hondurena", "hondureno", "honduran", "tegucigalpa"],
    "Nicaragua": ["nicaragua", "nicaraguense", "nicaraguan", "managua"],
    "Paraguay": ["paraguay", "paraguaya", "paraguayo", "paraguayan", "asuncion"],
    "Bolivia": ["bolivia", "boliviana", "boliviano", "bolivian", "la paz, bolivia", "santa cruz de la sierra"],
    "Venezuela": ["venezuela", "venezolana", "venezolano", "venezuelan", "caracas"],
    "Puerto Rico": ["puerto rico", "puertorriquena", "puerto rican", "san juan, puerto rico"],
    "Cuba": ["cuba", "cubana", "cubano", "la habana", "havana"],
    "Brasil": ["brasil", "brazil", "brasilena", "brasileno", "brazilian", "sao paulo", "rio de janeiro",
               "florianopolis", "belo horizonte"],
}

_PATTERNS = {c: re.compile(r"\b(" + "|".join(re.escape(t) for t in ts) + r")\b") for c, ts in _TERMS.items()}

# Ciudades ambiguas que sólo cuentan si no hay otro país detectado
_AMBIG = {"Chile": re.compile(r"\bsantiago\b"), "Perú": re.compile(r"\blima\b")}


def countries_in(text: str | None) -> list[str]:
    if not text:
        return []
    t = strip_accents(text).lower()
    hits = []
    for c, p in _PATTERNS.items():
        m = p.search(t)
        if m:
            hits.append((m.start(), c))
    if not hits:
        for c, p in _AMBIG.items():
            m = p.search(t)
            if m:
                hits.append((m.start(), c))
    return [c for _, c in sorted(hits)]


def country_from_text(text: str | None) -> str | None:
    cs = countries_in(text)
    return cs[0] if cs else None


def normalize_country(name: str | None) -> str | None:
    """Mapea la salida libre del LLM ('Mexico', 'méxico', 'MX') al nombre canónico."""
    if not name:
        return None
    iso = {"MX": "México", "CO": "Colombia", "CL": "Chile", "AR": "Argentina", "PE": "Perú", "UY": "Uruguay",
           "EC": "Ecuador", "CR": "Costa Rica", "GT": "Guatemala", "PA": "Panamá", "DO": "República Dominicana",
           "SV": "El Salvador", "HN": "Honduras", "NI": "Nicaragua", "PY": "Paraguay", "BO": "Bolivia",
           "VE": "Venezuela", "PR": "Puerto Rico", "CU": "Cuba", "BR": "Brasil"}
    if name.strip().upper() in iso:
        return iso[name.strip().upper()]
    return country_from_text(name) or name.strip()
