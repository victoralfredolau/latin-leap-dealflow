# Metodología y defensa de decisiones

## 1. Cómo leí el problema

- **La meta es +10 % sobre 60 deals/mes = 6 deals incrementales al mes** (≈ 1.4 por semana). No es un problema de volumen.
- El reto subraya que el equipo es pequeño y que **la calidad pesa más que el volumen bruto**. Una lista de mil
  startups sin filtrar *resta* capacidad. Por eso la herramienta entrega pocos deals, priorizados y con contexto.
- **Definición operativa de "deal calificado nuevo"** (la métrica que mide el +10 %):
  1. startup concreta e identificable (no notas de ecosistema, eventos, fondos o corporativos);
  2. en tesis: país de LATAM hispanohablante, etapa ≤ Serie A, base tecnológica;
  3. prioridad A (score ≥ 75) o B (≥ 60);
  4. **no** presente en el pipeline existente ni en el portafolio del fondo (`data/pipeline_existente.csv`).

### Sin acceso al CRM: el portafolio público como aproximación

No tengo la base de deals de Latin Leap (es un reto de selección). Para que la métrica no cuente empresas que el fondo
ya conoce, `data/pipeline_existente.csv` se carga con las **22 empresas de su portafolio** listadas por el agregador
F4 Fund (https://f4.fund/firms/latinleap-vc, consultado el 23-oct-2026): Razor Group, Habi, Vozy, Keybe, Magneto365,
Luable, ZUZU Hospitality, Refurbi, Carryt, Cubo Pago, Bacu, Dapta.ai, Scircle, Punto Post, TripWip, Morado, Rintin,
FANtium, StyleWork, Talkpush, Netux y Tennders.

- **Limitaciones:** es una fuente de terceros, no verificada contra latinleap.vc, y es solo el portafolio, no el
  pipeline completo (deals vistos y descartados). Por eso la métrica es *nueva para la herramienta y fuera del
  portafolio*; se vuelve estrictamente incremental el día que se conecte el export del CRM.
- **Cómo se conecta el CRM:** agregar filas `empresa,sitio_web,fuente` al mismo CSV (fuente vacía = "Pipeline CRM").
  El tablero etiqueta cada coincidencia con su origen y la excluye del KPI.
- **Validación inesperada:** en la prueba, el motor detectó por su cuenta a **Dapta** (ronda seed de USD 6M liderada
  por Chingona Ventures, según LatamList) y le asignó prioridad **A con 86/100**. Dapta aparece en el portafolio de
  Latin Leap en el listado de F4 Fund. Es un solo caso, no una prueba estadística, pero indica que el scoring encuentra
  el tipo de empresa en el que el fondo sí invierte. Ahora aparece etiquetada "Portafolio Latin Leap" y no suma a la meta.
- **Argumento adicional de incrementalidad (hipótesis):** las señales de Y Combinator, Get on Board y Hacker News
  aparecen antes de que haya prensa o inbound, por lo que es menos probable que el fondo ya las conozca. Se valida
  midiendo, con el CRM conectado, qué porcentaje de deals A/B ya existía.
- **Por qué outbound:** de las tres vías de dealflow de un fondo early-stage (inbound, red, outbound), el outbound es
  el que más escala con código y el que un equipo pequeño suele tener menos cubierto. El inbound depende de marca y
  la red de relaciones; ninguna de las dos se automatiza bien en 48 h.

## 2. Fuentes y por qué cada una

| Fuente | Tipo de señal | Por qué | Verificación previa |
|---|---|---|---|
| LatamList (RSS) | Rondas anunciadas | Medio en inglés dedicado a startups LATAM; publica rondas pre-seed/seed a diario | Feed válido consultado el 23-oct-2026 (10 ítems, p. ej. Fronte pre-seed, Dapta seed) |
| Contxto (RSS) | Rondas y perfiles | Medio en español del ecosistema | Feed consultado el 23-oct-2026 |
| Startupeable, TechCrunch LatAm, Pulso Social (RSS) | Rondas, lanzamientos | Cobertura complementaria | Se valida en la primera corrida (tablero → Salud de fuentes) |
| Startups Latam (RSS) | Rondas y noticias del ecosistema, en español | Cobertura de rondas pre-seed/seed hispanohablantes; repite notas de LatamList, lo que suma evidencia (+0.2 en Señal) | Feed válido consultado el 23-oct-2026 (p. ej. ronda de US$6M de startup colombiana de IA) |
| Techla Media (RSS) | Rondas, fondos y startups, sobre todo México | Medio en español de negocios e innovación con sección de startups y VC | El feed bloqueó la verificación externa; se confirma en la primera corrida |
| Google News (18 búsquedas de rondas) | Rondas en prensa local | Cubre medios nacionales que los especializados no cubren (p. ej. prensa de Perú, Uruguay, Centroamérica) | Ídem |
| Google News (19 búsquedas de red) | Generaciones de aceleradoras (Start-Up Chile, Platanus, Parallel18, 500 Global, Wayra, Google for Startups), incubadoras universitarias, fondos pre-seed (Latitud Ventures), CORFO, iNNpulsa, concursos y demo days | Convierte el networking en un canal sistemático: cada aceleradora y fondo pre-seed es un nodo de la red. Los portafolios pre-seed son los próximos deals seed | No probadas en vivo desde el entorno de construcción; se validan en la primera corrida |
| Y Combinator (dataset público yc-oss) | Aceleradora top | Señal de calidad alta; filtra compañías activas de países en tesis lanzadas en los últimos 18 meses | Consultado el 23-oct-2026: 6 compañías en tesis (p. ej. Sintropix, Chile, Fall 2026) |
| Hacker News (API de Algolia) | Lanzamientos | Founders técnicos LATAM publican "Show HN" antes de levantar capital | Se valida en la primera corrida |
| Get on Board (API pública) | Contratación tech | Una startup chica contratando su primer equipo técnico es señal temprana, a menudo previa a la ronda | Se valida en la primera corrida |

**Exclusiones deliberadas:** LinkedIn y X (términos de uso prohibitivos para scraping), Crunchbase/Dealroom
(de pago; se pueden enchufar si el fondo ya tiene licencia).

## 3. Pipeline

1. **Captura** (`dealflow/sources/`): cada fuente es independiente; si una falla, se registra y la corrida sigue.
2. **Pre-filtro** (`pipeline.prefilter`): descarta notas cuyo único país detectado es Brasil y noticias sin indicio
   de ronda, lanzamiento o aceleradora. Ahorra costo de LLM.
3. **Extracción** (`extract.py`): Claude Haiku 4.5 recibe lotes de 10 señales y devuelve JSON estructurado. El prompt
   exige **no inventar** campos ausentes (null), distinguir startup protagonista de notas genéricas, y justificar la
   calificación cualitativa. Si no hay API key o la llamada falla, un motor de reglas (regex de verbos de ronda,
   etapas, montos y gentilicios en ES/EN) produce los mismos campos con calidad neutral.
   **Notas con varias startups:** si una señal nombra varias startups (una generación de aceleradora, ganadores de un
   concurso), Claude devuelve un objeto por startup, hasta 15, sólo con nombres que aparecen en el texto. Cada una se
   vuelve un deal con la misma evidencia. Limitación: Google News entrega sólo el título y un extracto corto, así que
   la lista completa sólo se captura cuando la fuente la incluye en el texto del feed; leer el artículo completo es
   una mejora pendiente.
4. **Deduplicación** (`models.company_key`, `pipeline.merge`): por dominio del sitio y por nombre normalizado
   (sin acentos ni sufijos legales). Una startup vista en LatamList y en Google News es un deal con dos evidencias,
   lo que además sube su score.
5. **Score** (`scoring.py`), con pesos editables en `config/thesis.yaml`:

| Componente | Peso | Regla |
|---|---|---|
| Geografía | 25 | País en tesis = 100 %; no identificado = 30 %; fuera = 0 % y "Fuera de tesis" |
| Etapa | 25 | Pre-seed/seed 100 %, idea 60 %, desconocida 50 %, Serie A 30 %, Serie B+ 0 % y "Fuera de tesis" |
| Tecnología | 15 | Base tecnológica 100 %, desconocida 50 %, no tech 0 % y "Fuera de tesis" |
| Señal | 15 | Aceleradora 0.6, contratación/lanzamiento 0.4, noticia 0.3; +0.3 si hay ronda o inversionistas; +0.2 si ≥ 2 fuentes; +0.1 si ≤ 14 días (tope 1) |
| Calidad | 20 | Juicio del LLM 0–10 basado sólo en evidencia (inversionistas, aceleradora, tracción, mercado) |

   Prioridad **A ≥ 75** (contactar esta semana), **B ≥ 60** (revisar), **C < 60** (archivo).
6. **Métricas** (`pipeline.metrics`): deals calificados nuevos por fecha de la evidencia (no por fecha de corrida,
   para que la primera corrida no infle el número), avance contra la meta e incremento sobre el baseline.
7. **Publicación** (`site.py`): tablero estático en `docs/` + CSV + JSON; commit automático de `data/` y `docs/`.

## 4. Evidencia de funcionamiento (prueba local, 23-oct-2026)

Corrida sobre el snapshot real de LatamList y Contxto (16 ítems) más Y Combinator en vivo, **con el motor de reglas**
(sin API key en el entorno de construcción):

- 22 señales → 15 deals únicos → 11 con prioridad A o B. **Dapta se excluye por estar en el portafolio**, así que
  quedan **10 calificados nuevos**, de los cuales **4 tienen evidencia en los últimos 30 días** (Giraffe Bio,
  EFY Finance, Fronte, Rebill): 67 % de la meta mensual de 6, con sólo dos medios y sin LLM.
- Correctamente marcados **fuera de tesis**: Scanntech (ronda de USD 180M), Jeeves (USD 110M). Descartadas en
  pre-filtro: notas sólo de Brasil (Caju, Alice, Imersa) y notas de ecosistema (Mexico Tech Week, convocatorias,
  Kolors). El reporte "Aumenta la inversión en startups…" pasó el pre-filtro pero fue rechazado como no-oportunidad.
- **Limitación visible del motor de reglas:** Type One Energy (fusión nuclear en EE. UU., USD 200M) y Flai (con sede
  en San Francisco, founders uruguayos, Serie A de USD 27M) quedaron en **C** en lugar de "Fuera de tesis", porque
  las reglas no detectan el país ni el monto escrito como "200 millones de dólares". Es justo el caso que resuelve la
  extracción con Claude; por eso la API key es la configuración recomendada.
- 11/11 pruebas automáticas pasan (`python -m pytest -q`), incluida la ruta del LLM con cliente simulado y su
  respaldo ante fallas.

Lectura: sólo dos de siete fuentes, en una sola corrida y sin LLM, ya producen 4 deals calificados nuevos con
evidencia reciente, frente a una meta de 6/mes. No extrapolo un número para el conjunto completo; la cifra real la da el KPI
"Calificados nuevos · 30 días" después de las primeras corridas en producción.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Falsos positivos (notas que no son deals) | Pre-filtro, `es_oportunidad` del LLM, umbral B ≥ 60, y revisión humana antes de contactar |
| Deals ya conocidos inflando la métrica | Portafolio público precargado en `pipeline_existente.csv` (etiqueta "Portafolio Latin Leap", excluido del KPI); export del CRM el día uno |
| Sesgo hacia startups con prensa | Fuentes de señal temprana sin prensa: Get on Board, Hacker News, YC |
| Cambio de formato de una fuente | Parsers defensivos, salud de fuentes visible, cada fuente aislada |
| Costo del LLM | Haiku, lotes de 10, caché de señales procesadas, tope de 200 señales/corrida y de 15 startups por señal |
| Alucinación del LLM | Prompt con "null si no aparece", evidencia enlazada en cada deal, desglose del score visible |

## 6. Siguientes pasos (fase 2)

1. **Cerrar el loop:** que el equipo marque cada deal (contactado, primera llamada, descartado) en Airtable o en el
   CRM, y usar esas etiquetas para recalibrar pesos y el prompt de calidad.
2. **Alertas:** correo o Slack con los A nuevos de la semana.
3. **Más fuentes de señal temprana:** generaciones de aceleradoras locales (Startup Chile, Platanus, Wayra, 500),
   Product Hunt (requiere token), registros de dominios.
4. **Enriquecimiento de founders** con fuentes permitidas, para priorizar perfiles repetidores o de empresas top.

## 7. Guion sugerido para la demo (30 min)

1. **(3 min) Problema:** +10 % = 6 deals/mes; la calidad manda; definición de deal calificado y cómo se aproxima sin su CRM
   (portafolio público; caso Dapta).
2. **(10 min) En vivo:** *Actions → Run workflow*; mientras corre, recorrer el tablero: KPIs, filtros, un deal A con
   su evidencia, desglose y mensaje; salud de fuentes.
3. **(7 min) Cómo está construido:** arquitectura, `thesis.yaml` (cambiar un peso + `--rescore`), prompt, dedup.
4. **(10 min) Decisiones y riesgos:** por qué outbound, por qué estas fuentes y no LinkedIn, costo, métricas, fase 2.
