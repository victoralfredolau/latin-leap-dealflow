"""CLI: python -m dealflow [--solo yc,rss] [--fixtures archivo.json] [--rescore]"""
import argparse
import json
import logging
from pathlib import Path

from .pipeline import run

p = argparse.ArgumentParser(description="Motor de dealflow de Latin Leap")
p.add_argument("--solo", help="fuentes a correr, separadas por coma: rss,google_news,yc,hackernews,getonbrd")
p.add_argument("--fixtures", type=Path, help="JSON de señales de prueba (sin red)")
p.add_argument("--rescore", action="store_true", help="sólo recalcula scores y tablero (tras editar la tesis)")
a = p.parse_args()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
res = run(only=set(a.solo.split(",")) if a.solo else None, fixtures=a.fixtures, rescore_only=a.rescore)
print(json.dumps({k: v for k, v in res.items() if k != "fuentes"}, ensure_ascii=False, indent=1))
for f in res["fuentes"]:
    print(("OK  " if f["ok"] else "FALLA ") + f"{f['fuente']}: {f['senales']} señales" + (f" — {f['error']}" if f["error"] else ""))
