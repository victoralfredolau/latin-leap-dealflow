"""Construye tests/fixtures/snapshot_2026-10-23.json a partir de ítems REALES de los RSS de LatamList y
Contxto consultados el 23-oct-2026 (para probar el motor sin red). No es data inventada."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dealflow.models import Signal
from email.utils import parsedate_to_datetime
raw = json.loads(Path(__file__).with_name("rss_items_2026-10-23.json").read_text(encoding="utf-8"))
out = []
for src, items in raw.items():
    for it in items:
        if not it.get("link"):
            continue
        out.append(Signal(source=src, source_type="noticia", title=it["title"], url=it["link"],
                          published_at=parsedate_to_datetime(it["pubDate"]).isoformat(),
                          summary=it.get("description") or "").to_dict())
Path(__file__).with_name("snapshot_2026-10-23.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(out), "señales")
