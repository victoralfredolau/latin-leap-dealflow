"""Genera el tablero estático en docs/ (servido por GitHub Pages)."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
TEMPLATE = Path(__file__).parent / "templates" / "dashboard.html"

CSV_COLS = ["prioridad", "score", "empresa", "pais", "ciudad", "etapa", "sector", "monto_usd", "sitio_web",
            "fundadores", "inversionistas", "resumen", "razon", "fecha_evidencia", "primera_vista", "fuentes",
            "url_principal", "conocido", "conocido_fuente", "motor"]


def _public(d: dict) -> dict:
    keep = ["key", "empresa", "sitio_web", "pais", "ciudad", "sector", "etapa", "monto_usd", "inversionistas",
            "fundadores", "tecnologia", "calidad", "resumen", "razon", "mensaje", "score", "desglose",
            "prioridad", "en_tesis", "conocido", "conocido_fuente", "primera_vista", "fecha_evidencia", "ultima_senal", "senales",
            "motor"]
    return {k: d.get(k) for k in keep}


def build_site(deals: dict, metrics: dict, thesis: dict) -> None:
    DOCS.mkdir(exist_ok=True)
    rows = sorted((_public(d) for d in deals.values()),
                  key=lambda d: (d["prioridad"] not in ("A", "B"), -(d["score"] or 0)))
    payload = {"deals": rows, "metricas": metrics,
               "tesis": {"paises": thesis["paises_tesis"], "pesos": thesis["pesos"],
                         "umbrales": thesis["prioridad"], "fondo": thesis["fondo"]}}
    blob = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / "deals.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    with (DOCS / "deals.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for d in rows:
            w.writerow({
                **{k: d.get(k) for k in CSV_COLS if k in d},
                "fundadores": "; ".join(d.get("fundadores") or []),
                "inversionistas": "; ".join(d.get("inversionistas") or []),
                "fuentes": "; ".join(sorted({s["fuente"] for s in d.get("senales") or []})),
                "url_principal": (d.get("senales") or [{}])[0].get("url"),
            })
