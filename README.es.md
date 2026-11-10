[English](README.md) · **Español**

# leyes-federales-mx

[![CI](https://github.com/bajalabs/leyes-federales-mx/actions/workflows/ci.yml/badge.svg)](https://github.com/bajalabs/leyes-federales-mx/actions/workflows/ci.yml)
[![Código: MIT](https://img.shields.io/badge/c%C3%B3digo-MIT-blue.svg)](LICENSE)
[![Datos: CC0-1.0](https://img.shields.io/badge/datos-CC0--1.0-lightgrey.svg)](LICENSE-DATA)
[![Última versión](https://img.shields.io/github/v/release/bajalabs/leyes-federales-mx)](https://github.com/bajalabs/leyes-federales-mx/releases/latest)

Las 319 leyes federales mexicanas que publica la Cámara de Diputados, convertidas desde los archivos Word oficiales en datos estructurados y buscables — Markdown que se lee en GitHub, una base SQLite con búsqueda de texto completo y CSV — para desarrolladores, investigadores, periodistas y abogados que necesitan el derecho mexicano como datos.

Cada artículo sabe a qué ley pertenece, su lugar en la estructura (libro, título, capítulo, sección), sus fracciones e incisos, las reformas que lo tocaron con sus fechas en el Diario Oficial de la Federación (DOF), y los artículos y leyes que cita. Cada ley está anclada por sha256 al archivo oficial del que proviene.

## Qué contiene

Captura del 26 de agosto de 2026 desde [diputados.gob.mx/LeyesBiblio](https://www.diputados.gob.mx/LeyesBiblio/index.htm), con las dos leyes que se volvieron a publicar desde entonces (la Constitución y la LIGIE) capturadas de nuevo el 10 de noviembre de 2026. Los conteos corresponden al texto vigente de cada ley:

| | |
|---|---|
| leyes | **319**: 310 vigentes, 4 abrogadas, 5 invalidadas por la Suprema Corte |
| tipos | 1 constitución, 9 códigos, 301 leyes, 3 reglamentos, 1 estatuto y 4 más (los presupuestos de egresos 2025 y 2026, la Ordenanza General de la Armada y una ley de impuestos) |
| archivos fuente | 638 (un .doc y un .pdf por ley), 417 MB, cada uno anclado por URL y sha256; los 4 archivos de la captura anterior de las dos leyes recapturadas siguen anclados |
| artículos | **59,549**: 42,721 artículos ordinarios y 16,828 transitorios |
| partes de artículo | 203,339 párrafos, fracciones, incisos y numerales |
| divisiones | 10,278 libros, títulos, capítulos, secciones y apartados |
| notas de reforma | 37,487 ("Artículo reformado DOF 14-08-2001"); el 99.82 % se descompone en acción y fechas ISO |
| citas | 30,009 referencias entre artículos y leyes; el 99.95 % resuelto a su destino |
| bloques | 287,829 párrafos clasificados: el registro sin pérdida del que se deriva todo lo demás |
| texto normativo | 46.5 millones de caracteres |

## Qué cambió desde la captura anterior

La base guarda cada captura de una ley como su propia `law_version` y compara capturas consecutivas artículo por artículo en `version_diffs` y `article_changes`. Al 10 de noviembre de 2026, la Cámara había vuelto a publicar dos leyes capturadas el 26 de agosto:

| Ley | Última reforma, antes → después | Agregados | Modificados | Eliminados | Sin cambio |
|---|---|---|---|---|---|
| Constitución (`001-cpeum`) | DOF 02/06/2026 → DOF 07/10/2026 | 7 | 3 | 0 | 925 |
| LIGIE 2022 (`078-ligie_2022`) | DOF 29/12/2025 → DOF 29/12/2025 | 2 | 0 | 0 | 81 |

La reforma constitucional del 7 de octubre de 2026 (nacionalidad única para la titularidad de los Poderes Ejecutivos Federal y locales) modifica los artículos 82, 116 y 122 y agrega su decreto: un artículo y seis transitorios. La LIGIE sumó un decreto que modifica temporalmente el arancel de importación de una fracción arancelaria: un artículo y un transitorio.

```sql
-- cada artículo de la Constitución que cambió entre sus dos capturas
SELECT c.change_type, c.article_key, round(c.similarity, 3) AS similarity, substr(c.diff, 1, 300) AS diff
FROM article_changes c
JOIN version_diffs d ON d.id = c.version_diff_id
JOIN laws l         ON l.id = d.law_id
WHERE l.slug = '001-cpeum' AND c.change_type <> 'unchanged'
ORDER BY c.change_type, c.id;
```

El Markdown de `data/leyes/` muestra siempre el texto vigente; el historial de git y los bloques de la captura anterior (en `data/leyes/<slug>/history/<fecha>/` y en el archivo de bloques) conservan el previo.

## Inicio rápido

Se necesita Python 3.12 o posterior y nada más (solo la biblioteca estándar). La herramienta de línea de comandos `sqlite3` es cómoda para consultar; viene con macOS, y en Debian o Ubuntu es `apt install sqlite3`.

**Leer una ley.** Cada ley es un archivo Markdown en [`data/leyes/`](data/leyes): la Constitución es [`data/leyes/001-cpeum/CPEUM.md`](data/leyes/001-cpeum/CPEUM.md).

**Consultar la base de datos.** Descárgala de la [última versión](https://github.com/bajalabs/leyes-federales-mx/releases/latest):

```bash
curl -LO https://github.com/bajalabs/leyes-federales-mx/releases/latest/download/leyes-federales-mx.sqlite.zip
python3 -m zipfile -e leyes-federales-mx.sqlite.zip .
sqlite3 leyes-federales-mx.sqlite "SELECT label, substr(text, 1, 120) FROM v_articles
  WHERE law_slug = '001-cpeum' AND numero_int = 1 AND is_transitorio = 0;"
```

**Construirla tú mismo.** Desde un clon, reconstruye la base a partir de los bloques publicados en unos 20 segundos y pasa la verificación:

```bash
git clone https://github.com/bajalabs/leyes-federales-mx.git
cd leyes-federales-mx
python3 -m unittest                                   # las pruebas, unos 2 segundos
python3 scripts/build_db.py --sample                  # 6 leyes de la muestra incluida, sin red
python3 scripts/verify_db.py --sample
curl -LO https://github.com/bajalabs/leyes-federales-mx/releases/latest/download/leyes-federales-mx-blocks.zip
python3 -m zipfile -e leyes-federales-mx-blocks.zip .   # se desempaca en data/leyes/
python3 scripts/build_db.py                           # las 319 leyes -> build/leyes-federales-mx.sqlite
python3 scripts/verify_db.py                          # PASS, con un recibo JSON en build/verify.json
```

`uv run scripts/build_db.py` también funciona. Cada ruta y URL tiene una opción y una variable de entorno (`--data`/`LEYES_DATA_DIR`, `--db`/`LEYES_DB`, `LEYES_BUILD_DIR`, `LEYES_DIST_DIR`, `LEYES_BASE_URL`, `LEYES_USER_AGENT`); cualquier script acepta `--help`.

## Archivos de cada versión

| Archivo | Qué es |
|---|---|
| `leyes-federales-mx.sqlite.zip` | la base de datos (290 MB desempacada) |
| `leyes-federales-mx-blocks.zip` | el `<CODE>.blocks.jsonl` de cada captura, en su ruta bajo `data/leyes/` (las capturas anteriores bajo `history/<fecha>/`) |
| `leyes-federales-mx-laws.csv` | una fila por ley: nombres, vigencia, fechas, URL y sha256 de la fuente, conteos |
| `leyes-federales-mx-articles.csv.zip` | una fila por artículo del texto vigente de cada ley: ley, clave, etiqueta, estructura, última reforma, texto completo |
| `SHA256SUMS` | verifica las descargas con `sha256sum -c SHA256SUMS` (o `shasum -a 256 -c`) |

Los CSV están en UTF-8 con entrecomillado estándar; los textos conservan sus saltos de párrafo dentro de campos entre comillas. En Excel, ábrelos con Datos > Desde texto/CSV y elige UTF-8.

## Estructura del repositorio

```
leyes-federales-mx/
├── data/
│   ├── manifest.json            cada ley: nombres, vigencia, fechas, y URL + sha256 + tamaño de su .doc y .pdf
│   ├── conversion-report.json   qué edición (DOC o PDF de respaldo) produjo cada ley
│   ├── sample.txt               las 6 leyes cuyos bloques van en git, para la CI
│   └── leyes/<numero>-<nombre_corto>/       p. ej. 001-cpeum, 035-lce, 314a-pef_2025
│       ├── <CODE>.md            la ley en Markdown, con un encabezado de procedencia
│       ├── meta.json            la entrada de esta ley en el manifiesto, con previous_captures si se volvió a capturar
│       ├── convert.json         edición usada, conteo de bloques, índice de mojibake
│       ├── <CODE>.blocks.jsonl  párrafos clasificados (archivo de la versión; fuera de git)
│       ├── history/<fecha>/     bloques y convert.json de una captura anterior, si la hay
│       └── source/              el .doc y el .pdf oficiales (se descargan a pedido; fuera de git)
├── db/schema.sql                el esquema SQLite: tablas, vistas, índice de texto completo
├── scripts/                     el proceso, en Python de biblioteca estándar
├── tests/                       python3 -m unittest
├── build/                       la base de datos y los recibos (fuera de git)
└── dist/                        los archivos de la versión (fuera de git)
```

Las carpetas se llaman `<numero>-<nombre_corto>` como las lista la Cámara; los tres números con letra (`060 A`, `120 A`, `314 A`) quedan como `060a`, `120a`, `314a`. `<CODE>` es el código de archivo de la Cámara (`CPEUM`, `LAdua`, `28`).

## Esquema

```
jurisdictions ─< corpora ─< laws ─< law_versions ─┬─< divisions          (árbol autorreferenciado)
                                                   ├─< articles ─< article_parts
                                                   ├─< annotations      (notas de reforma, fechas DOF)
                                                   ├─< cross_references (el grafo de citas)
                                                   └─< blocks           (registro sin pérdida)

law_versions ─< version_diffs ─< article_changes     (cambios entre capturas)
articles_fts                                          (índice FTS5 de texto completo)
```

| Tabla o vista | Qué es una fila |
|---|---|
| `laws` | la identidad estable de una ley: `slug` (`001-cpeum`), `nombre`, `tipo`, `estado_vigencia`, `dof_original` |
| `law_versions` | una edición capturada: `source_kind` (`doc`/`pdf`), `resolved_url`, `source_sha256`, `ultima_reforma` |
| `articles` | `article_key` es la identidad entre ediciones: `'27'`, `'15-bis'`, `'195-z-1'`, `'77-bis-35-a'`, `'T[03]:primero'` (transitorio del tercer bloque de decreto), `'T[04]:d:primero'` (artículo del cuerpo de un decreto de reforma). `text` es solo texto normativo; `last_reform_date` es la fecha DOF más reciente de sus notas |
| `article_parts` | `kind` es `parrafo`, `fraccion`, `inciso` o `numeral`, con su `label` (`I`, `a)`, `1.`) |
| `annotations` | las notas editoriales de reforma, fuera del texto normativo: `target_kind`, `action` (`reformado`, `adicionado`, `derogado`, …), `dof_dates` (arreglo JSON de fechas ISO) |
| `cross_references` | una cita hallada en un artículo, con la `quote` literal: `ref_kind` es `self-article` ("artículo 27 de esta Ley"), `constitution` ("artículo 131 constitucional") o `law` (otra ley nombrada completa) |
| `blocks` | cada párrafo clasificado con sus rasgos de estilo, para reconstruir las tablas derivadas sin volver a convertir |
| `v_laws`, `v_articles`, `v_toc`, `v_reformas` | vistas de un salto sobre la versión vigente (la más reciente) de cada ley |

`articles_fts` ignora acentos: `importacion` encuentra `importación`.

## Recetario de consultas

```sql
-- un artículo con su lugar en la estructura
SELECT law_slug, label, division_heading, division_rubric, last_reform_date
FROM v_articles
WHERE law_slug = '001-cpeum' AND numero_int = 27 AND is_transitorio = 0;

-- búsqueda de texto completo en las 319 leyes (sin importar acentos)
SELECT l.nombre_corto, a.label, snippet(articles_fts, 1, '«', '»', '…', 12) AS hit
FROM articles_fts f
JOIN articles a ON a.id = f.rowid
JOIN laws l     ON l.id = a.law_id
WHERE articles_fts MATCH '"comercio exterior"'
ORDER BY rank LIMIT 20;

-- el índice de una ley
SELECT printf('%.*c', depth * 2, ' ') || heading AS heading, rubric, descendant_article_count
FROM v_toc WHERE law_slug = '035-lce' ORDER BY seq;

-- las fracciones de un artículo
SELECT p.kind, p.label, p.text
FROM article_parts p JOIN v_articles a ON a.id = p.article_id
WHERE a.law_slug = '035-lce' AND a.article_key = '4' ORDER BY p.seq;

-- presión de reforma: los artículos más reformados
SELECT l.nombre_corto, a.label, count(*) AS reforms
FROM annotations n
JOIN articles a ON a.id = n.article_id
JOIN laws l     ON l.id = a.law_id
GROUP BY a.id ORDER BY reforms DESC LIMIT 20;

-- todo lo reformado en 2026, en todo el corpus
SELECT law_slug, article_label, action, dof_dates
FROM v_reformas WHERE dof_dates LIKE '%"2026-%';

-- qué cita el artículo 27 constitucional
SELECT quote, target_article_key FROM cross_references
WHERE article_id = (SELECT id FROM v_articles
                    WHERE law_slug = '001-cpeum' AND numero_int = 27 AND is_transitorio = 0);

-- las leyes más citadas por otras leyes
SELECT t.slug, count(*) AS citations
FROM cross_references x
JOIN laws t         ON t.id = x.target_law_id
JOIN law_versions v ON v.id = x.law_version_id
WHERE v.law_id <> t.id
GROUP BY t.id ORDER BY citations DESC LIMIT 10;

-- leyes que ya no están vigentes
SELECT slug, nombre, estado_vigencia, ultima_reforma FROM v_laws WHERE estado_vigencia <> 'vigente';

-- cada captura de una ley y los conteos de cambio entre capturas consecutivas
SELECT v.captured_at, v.ultima_reforma, v.source_sha256, d.n_added, d.n_modified, d.n_removed
FROM law_versions v LEFT JOIN version_diffs d ON d.to_version_id = v.id
WHERE v.law_id = (SELECT id FROM laws WHERE slug = '001-cpeum') ORDER BY v.captured_at;
```

`sqlite3 -json` o `-csv` convierten cualquiera de estas consultas en JSON o CSV. [Datasette](https://datasette.io) y [DB Browser for SQLite](https://sqlitebrowser.org) abren el archivo tal cual.

## Cómo se construye

```
fetch.py ──> source/<CODE>.doc, .pdf ──> convert_all.py ──> <CODE>.blocks.jsonl ──> build_db.py ──> SQLite ──> verify_db.py
 (sha256 contra manifest.json)           (doc_to_md.py; respaldo   + <CODE>.md            (patterns.py)            (la compuerta)
                                          pdf_to_md.py)
```

1. **Descarga.** [`scripts/fetch.py`](scripts/fetch.py) baja el `.doc` y el `.pdf` de cada ley desde la Cámara de Diputados y los compara con el sha256 de `data/manifest.json`. La Cámara sobrescribe el archivo en cada reforma y mueve las leyes abrogadas a `/abro/`, así que cada descarga recorre una escalera de URL conocidas y registra la que respondió. `--recapture` adopta un archivo que cambió y mueve la captura anterior a `previous_captures` y a `history/<fecha>/`.
2. **Conversión.** [`scripts/convert_all.py`](scripts/convert_all.py) convierte cada `.doc` a HTML con `textutil` de macOS y clasifica cada párrafo ([`doc_to_md.py`](scripts/doc_to_md.py)): inicio de artículo, inicio de transitorio, encabezado, nota de reforma, nota, tabla o cuerpo. Los encabezados de página y los campos de número de página del Word, que `textutil` emite después del cuerpo, se clasifican como `furniture`: se conservan en `blocks` y quedan fuera de los artículos y del Markdown. Un control de salud mide el mojibake de cada conversión y recurre al PDF ([`pdf_to_md.py`](scripts/pdf_to_md.py), `pdftotext -layout`) cuando el Word no se puede leer.
3. **Construcción.** [`scripts/build_db.py`](scripts/build_db.py) construye cada captura de cada ley como una versión y compara capturas consecutivas. Recorre una vez los bloques de cada captura: mantiene la pila de divisiones, abre un artículo en cada inicio, separa el cuerpo en partes, adjunta las notas, descompone sus fechas DOF y extrae las citas. Una sola gramática, [`scripts/patterns.py`](scripts/patterns.py), sirve a todas las etapas: números de artículo con sufijos sucesivos (`8 Bis`, `195-Z-1`, `77 Bis 35 A`, `26-LL`, `257 Quintus`), transitorios ordinales (`DÉCIMO PRIMERO`), fronteras de decreto dentro de las zonas transitorias.
4. **Verificación.** [`scripts/verify_db.py`](scripts/verify_db.py) es la compuerta de regresión: integridad referencial, ninguna clave de artículo repetida entre artículos ordinarios, una alarma que confirma que cada encabezado de artículo del Markdown se volvió artículo, huecos de numeración, al menos 99 % de notas descompuestas, paridad del índice de texto completo, totales contra el manifiesto, pisos de artículos para leyes que alguna vez retrocedieron, que la versión vigente de cada ley sea la captura que ancla su manifiesto, y que ningún artículo termine con encabezados de página.

Cuando la gramática mejora, [`reclassify.py`](scripts/reclassify.py) vuelve a clasificar los bloques guardados y [`blocks_to_md.py`](scripts/blocks_to_md.py) regenera el Markdown: sin conversión, sin red, en cualquier sistema operativo. [`diff_versions.py`](scripts/diff_versions.py) compara dos capturas artículo por artículo y [`package_release.py`](scripts/package_release.py) escribe los archivos de la versión.

**Reproducible.** El 10 de noviembre de 2026, volver a descargar los archivos oficiales de dos leyes cuyos anclajes seguían vigentes y convertirlos de nuevo produjo Markdown y bloques idénticos byte por byte a los del repositorio.

### Por qué el Word y no el PDF

La Cámara publica cada ley en PDF y en Word. El PDF ha perdido el estilo que distingue las notas editoriales del texto normativo, y sus renglones de ancho fijo dejan referencias a mitad de oración al inicio de un renglón, donde parecen artículos nuevos. Medido en la Constitución (414 páginas, 136 artículos) en la captura de agosto de 2026:

| | DOC | PDF |
|---|---|---|
| fronteras de artículo halladas | **136 (exactas)** | 207 (71 falsas) |
| renglones de encabezado y pie por quitar | **0** | 1,656 |
| notas de reforma recuperadas | **975** | 120 |

En el Word, la Cámara compone las notas de reforma en letra pequeña azul alineada a la derecha y los encabezados centrados en negritas, así que clasificar es mecánico. Tres archivos Word no se pueden leer con `textutil` (la LIGIE de 2022 y los presupuestos de egresos 2025 y 2026); esos vienen del PDF, y `law_versions.source_kind` lo indica.

## Limitaciones conocidas

- **Una fotografía, no una transmisión en vivo.** El 10 de noviembre de 2026 los 638 archivos anclados coincidían con el sitio de la Cámara: 634 de la captura del 26 de agosto y los 4 recapturados ese día. La Cámara vuelve a publicar una ley en cada reforma; `python3 scripts/fetch.py` muestra qué ha cambiado desde entonces.
- **Las leyes nuevas no se agregan solas.** La lista de leyes viene del índice de la Cámara leído el 8 de marzo de 2026. Las leyes reformadas se actualizan con `fetch.py --recapture`; una ley publicada después de esa fecha necesita una entrada manual en el manifiesto hasta que exista un lector del índice.
- **Dos fechas de última reforma.** `law_versions.ultima_reforma` es la fecha que imprime la propia edición ("Últimas reformas publicadas DOF 02-06-2026") en las 250 leyes que la imprimen, y la del índice en las demás; `ultima_reforma_indice` conserva la del índice. Difieren en 31 leyes porque el índice se rezaga. `articles.last_reform_date` sale de las notas de cada artículo.
- **La conversión requiere macOS.** `textutil` solo viene con macOS. Reconstruir la base, regenerar el Markdown y volver a aplicar la gramática funcionan en cualquier sistema a partir de los bloques guardados.
- **Tres leyes vienen del PDF** (LIGIE 2022, PEF 2025, PEF 2026) y no tienen notas de reforma, porque el PDF no las distingue del texto. Son documentos dominados por tablas, donde eso importa menos.
- **Las tablas se aplanan.** Una tabla queda como una línea `| … |` por párrafo; las columnas no se reconstruyen.
- **Las partes de artículo se etiquetan por patrón.** Las fracciones en romanos y los incisos con letra son confiables; las listas muy anidadas o dentro de tablas quedan como `parrafo`.
- **Claves repetidas en zonas transitorias.** Quedan 333 grupos de `article_key` repetida dentro de zonas transitorias, donde las resoluciones de invalidez de la Suprema Corte repiten PRIMERO/SEGUNDO/TERCERO bajo un mismo encabezado sin frontera de decreto. Los artículos ordinarios no tienen ninguna (una compuerta de `verify_db.py`); `diff_versions.py` empareja el residuo por posición.
- **Los huecos de numeración de la OGA** (290) son renumeraciones de la propia fuente, verificadas contra el archivo oficial.
- **Las citas se hallan por patrón**: referencias a un artículo de la misma ley, a la Constitución y a otras leyes nombradas completas. Las abreviaturas y referencias vagas ("la Ley", "el Reglamento") no se resuelven; 14 de las 30,009 referencias halladas nombran un número de artículo que la ley no tiene.
- **Imágenes y ecuaciones son marcadores.** Una imagen dentro de un decreto aparece como su código de campo de Word (`import "http://…gif"`, 3 párrafos en 2 leyes) y una ecuación como `EMBED Equation.3`, seguida del texto que la explica.
- **El seguimiento de cambios apenas empieza.** Dos leyes tienen dos capturas; las otras 317 tienen una, así que `article_changes` solo cubre lo que cambió en esas dos.
- **No es una publicación oficial ni asesoría legal.** El texto con validez es el publicado en el [Diario Oficial de la Federación](https://www.dof.gob.mx). Revisa el archivo oficial antes de apoyarte en cualquier texto de aquí; su URL y su sha256 están en el encabezado de cada ley.

## Licencia

Código (scripts, pruebas, esquema, flujos de trabajo): [MIT](LICENSE). Datos (Markdown, metadatos, base de datos, bloques, CSV): [CC0 1.0](LICENSE-DATA), dedicados al dominio público.

Los textos de las leyes mexicanas no son objeto de derecho de autor: el artículo 14, fracción VIII, de la Ley Federal del Derecho de Autor excluye los textos legislativos y exige que, si se publican, se apeguen al texto oficial. Los anclajes sha256 existen para que cualquiera pueda comprobarlo. Ver [LICENSE-DATA](LICENSE-DATA).

## Cómo citar

Cita la ley misma por su nombre oficial y su publicación en el DOF. Para citar este conjunto de datos, usa los metadatos de [CITATION.cff](CITATION.cff) (GitHub muestra el botón "Cite this repository"), por ejemplo:

> Baja Labs (2026). *leyes-federales-mx: the Mexican federal laws as structured data* (versión 1.0.0, capturas del 2026-08-26 y del 2026-11-10) [Conjunto de datos]. https://github.com/bajalabs/leyes-federales-mx

## Cómo contribuir

Los reportes de un artículo mal partido, una nota de reforma perdida o una cita rota son la contribución más útil: abre un [error de datos](https://github.com/bajalabs/leyes-federales-mx/issues/new?template=data-error.yml) con la ley y el artículo. Las correcciones van a la gramática, nunca al Markdown a mano. [CONTRIBUTING.md](CONTRIBUTING.md) explica cómo construir, probar, actualizar el corpus y proponer un cambio; [SECURITY.md](SECURITY.md), cómo reportar una vulnerabilidad; [CHANGELOG.md](CHANGELOG.md), qué cambió.
