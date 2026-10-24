# Latin Leap · Motor de Dealflow

Herramienta automatizada que **aumenta el dealflow calificado de Latin Leap en ≥ 10 %** (≥ 6 deals nuevos/mes
sobre un baseline de 60) mediante sourcing *outbound*: detecta cada día startups pre-seed y seed de
LATAM hispanohablante en fuentes públicas, las clasifica contra la tesis del fondo con Claude, elimina
duplicados, les asigna un score 0–100 explicable y las publica en un tablero web con un borrador de primer
contacto listo para enviar.

- **Corre sola:** GitHub Actions la ejecuta todos los días a las 06:17 (CDMX). Cero operación manual.
- **Accesible:** tablero en GitHub Pages (`https://<usuario>.github.io/<repo>/`), CSV y JSON descargables.
- **Auditable:** cada corrida deja un commit con los datos (`data/`) y el tablero (`docs/`).
- **Robusta:** si una fuente cae, se marca en el tablero y el resto sigue; si el LLM falla, se usa un motor de reglas.

> Metodología, supuestos y defensa de las decisiones: ver [`METODOLOGIA.md`](METODOLOGIA.md).

---

## Arquitectura

```
 Fuentes públicas                    Motor (Python, GitHub Actions · diario)               Salida (GitHub Pages)
 ─────────────────                   ───────────────────────────────────────               ─────────────────────
 LatamList, Contxto, Startupeable ─┐
 TechCrunch LatAm, Pulso Social    │   1 Captura ─► 2 Pre-filtro ─► 3 Extracción (Claude)   Tablero web
 Google News (37 búsquedas)       ├─►   (RSS/API)   (Brasil, ruido)   empresa, país, etapa,  · KPIs vs. meta
 Y Combinator (dataset yc-oss)     │                                  ronda, founders,       · filtros y búsqueda
 Hacker News (Show/Launch HN)      │   ─► 4 Deduplicación ─► 5 Score 0–100 ─► 6 Métricas     · detalle + mensaje
 Get on Board (vacantes tech)     ─┘     (dominio/nombre)   (tesis.yaml)      (meta +10 %)   · salud de fuentes
                                                                                            deals.csv / deals.json
```

| Carpeta | Contenido |
|---|---|
| `config/thesis.yaml` | Tesis del fondo: países, etapas, pesos del score, umbrales, meta. **Se edita sin tocar código.** |
| `config/sources.yaml` | Fuentes y búsquedas. Agregar un RSS = agregar dos líneas. |
| `dealflow/` | Código del motor (`sources/`, `extract.py`, `scoring.py`, `pipeline.py`, `site.py`). |
| `data/` | Estado persistente: `deals.json`, `corridas.json`, `metricas.json`, `senales_procesadas.json` y `pipeline_existente.csv` (portafolio / CRM). |
| `docs/` | Tablero publicado por GitHub Pages (`index.html`, `deals.csv`, `deals.json`). |
| `tests/` | 11 pruebas (geo, dedup, reglas, score, LLM simulado y su respaldo, exclusión de portafolio, notas de cohorte con varias startups) + snapshot real de RSS del 23-oct-2026. |

---

## Puesta en marcha (≈ 10 minutos)

1. **Crear el repositorio** en GitHub (puede ser privado con GitHub Pro/Team, o público) y subir esta carpeta:
   ```bash
   git init && git add . && git commit -m "Motor de dealflow Latin Leap"
   git branch -M main
   git remote add origin https://github.com/<usuario>/latin-leap-dealflow.git
   git push -u origin main
   ```
2. **Cargar la API key de Claude** como secreto: *Settings → Secrets and variables → Actions → New repository
   secret* → nombre `ANTHROPIC_API_KEY`. (Opcional: variable `ANTHROPIC_MODEL`; por defecto `claude-haiku-4-5`.)
   Sin la key el motor funciona igual con reglas, pero sin calificación cualitativa ni borradores de mensaje.
3. **Activar Pages:** *Settings → Pages → Build and deployment → Source: GitHub Actions*.
4. **Permisos del workflow:** *Settings → Actions → General → Workflow permissions → Read and write permissions*.
5. **Primera corrida:** pestaña *Actions → Dealflow diario → Run workflow*. Al terminar (≈ 2–5 min), el link del
   tablero aparece en el resumen del job. A partir de ahí corre solo cada día.
6. **Empresas ya conocidas:** `data/pipeline_existente.csv` viene precargado con las 22 empresas del portafolio
   público de Latin Leap (fuente: F4 Fund; ver METODOLOGIA.md §1). Se etiquetan "Portafolio Latin Leap" y **no** suman a
   la meta. Cuando el fondo comparta el export de su CRM, se agregan filas `empresa,sitio_web,fuente` al mismo archivo
   y el +10 % pasa a medir sólo deals estrictamente incrementales.

### Correr localmente
```bash
pip install -r requirements.txt
python -m pytest -q                       # pruebas
python -m dealflow                        # corrida completa (todas las fuentes)
python -m dealflow --solo yc,rss          # sólo algunas fuentes
python -m dealflow --rescore              # recalcular scores tras editar config/thesis.yaml
python -m dealflow --fixtures tests/fixtures/snapshot_2026-10-23.json   # sin red
```
Abrir `docs/index.html` en el navegador.

---

## Qué ve el equipo

- **KPIs:** deals calificados nuevos en 30 días vs. meta (+6), incremento % sobre el baseline de 60, deals prioridad A, universo rastreado.
- **Tendencia semanal** contra la meta semanal (≈ 1.4), y distribución por país y por fuente.
- **Tabla filtrable** por prioridad, país, etapa y fuente, con búsqueda libre por empresa, sector, fundador o inversionista.
- **Detalle de cada deal:** resumen, justificación del score, desglose por componente, evidencia con links a la fuente original y **borrador de primer contacto** con botón de copiar.
- **Salud de fuentes y bitácora** de cada corrida (señales crudas, procesadas, deals nuevos, calificados nuevos).

## Costo de operación (estimado)

GitHub Actions y Pages: USD 0 en el plan gratuito para este volumen. Claude Haiku 4.5 cuesta USD 1 por millón de
tokens de entrada y USD 5 por millón de salida ([Anthropic](https://www.anthropic.com/claude/haiku)). Con ~450
tokens de entrada y ~250 de salida por señal (lotes de 10), cada señal cuesta ≈ USD 0.0017; con el tope de 200
señales/día el máximo es ≈ USD 10/mes, y en régimen (sólo señales nuevas) debería ser menor. Es una estimación
propia que se valida con el consumo real de la consola de Anthropic.
