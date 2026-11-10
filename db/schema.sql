-- ═══════════════════════════════════════════════════════════════════════════
-- leyes-federales-mx — the Mexican federal laws as a SQLite database
--
-- Design notes
--  * A LAW has a stable identity; a LAW_VERSION is one captured edition of it.
--    Everything derived (divisions/articles/parts/annotations/blocks) hangs off
--    a law_version, never off the law, so change tracking is a diff between two
--    rows instead of a destructive overwrite.
--  * Every text-bearing row carries text_sha256, so a diff compares hashes
--    first and runs the expensive similarity check only on the survivors.
--  * `blocks` is the lossless landing zone: every converted paragraph with its
--    style features. When the extractor improves, the derived tables are
--    rebuilt from it without downloading or converting anything again.
--  * The core tables use plain types. The FTS5 table at the bottom is the one
--    SQLite-specific piece.
-- ═══════════════════════════════════════════════════════════════════════════

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS jurisdictions (
  code        TEXT PRIMARY KEY,          -- 'MX'
  name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS corpora (
  id              INTEGER PRIMARY KEY,
  jurisdiction    TEXT NOT NULL REFERENCES jurisdictions(code),
  slug            TEXT NOT NULL,         -- 'leyes-federales'
  name            TEXT NOT NULL,
  source_url      TEXT,
  UNIQUE (jurisdiction, slug)
);

-- Stable identity of a legal instrument.
CREATE TABLE IF NOT EXISTS laws (
  id                INTEGER PRIMARY KEY,
  corpus_id         INTEGER NOT NULL REFERENCES corpora(id),
  slug              TEXT NOT NULL,       -- '001-cpeum'
  numero            TEXT,                -- the Cámara's list number: '001', '060 A'
  nombre            TEXT NOT NULL,
  nombre_corto      TEXT,                -- 'cpeum'
  codigo_archivo    TEXT,                -- file code on the Cámara site: 'CPEUM', '28'
  tipo              TEXT,                -- constitucion | ley | codigo | reglamento | estatuto | decreto | otro
  estado_vigencia   TEXT,                -- vigente | abrogada | invalidada
  dof_original      TEXT,                -- 'DOF 05/02/1917' as published
  url_detalle       TEXT,                -- the law's page on the Cámara site
  UNIQUE (corpus_id, slug)
);

-- One captured edition. Two captures with the same sha256 are the same version.
CREATE TABLE IF NOT EXISTS law_versions (
  id                INTEGER PRIMARY KEY,
  law_id            INTEGER NOT NULL REFERENCES laws(id) ON DELETE CASCADE,
  captured_at       TEXT NOT NULL,
  ultima_reforma    TEXT,                -- 'DOF 02/06/2026': as the edition itself prints it, else the index value
  reforma_date      TEXT,                -- ultima_reforma, ISO-normalised and sortable
  ultima_reforma_indice TEXT,            -- what the Cámara's list of laws said when it was read (it can lag)
  source_kind       TEXT NOT NULL,       -- 'doc' | 'pdf'
  resolved_url      TEXT,
  source_sha256     TEXT NOT NULL,       -- pins the official file the text came from
  source_bytes      INTEGER,
  converter         TEXT,                -- provenance of the extraction
  text_sha256       TEXT,                -- hash of the full converted text
  UNIQUE (law_id, source_kind, source_sha256)
);
CREATE INDEX IF NOT EXISTS ix_lv_law ON law_versions(law_id, reforma_date);

-- Libro / Título / Capítulo / Sección / Apartado — a self-referencing tree.
CREATE TABLE IF NOT EXISTS divisions (
  id              INTEGER PRIMARY KEY,
  law_version_id  INTEGER NOT NULL REFERENCES law_versions(id) ON DELETE CASCADE,
  parent_id       INTEGER REFERENCES divisions(id) ON DELETE CASCADE,
  kind            TEXT NOT NULL,         -- libro|titulo|capitulo|seccion|apartado|otro
  ordinal_label   TEXT,                  -- 'Primero', 'I', 'IV'
  heading         TEXT NOT NULL,         -- 'Título Primero'
  rubric          TEXT,                  -- 'De los Derechos Humanos y sus Garantías'
  depth           INTEGER NOT NULL,
  seq             INTEGER NOT NULL,      -- document order
  path            TEXT                   -- 'titulo-primero/capitulo-i'
);
CREATE INDEX IF NOT EXISTS ix_div_lv ON divisions(law_version_id, seq);

CREATE TABLE IF NOT EXISTS articles (
  id              INTEGER PRIMARY KEY,
  law_version_id  INTEGER NOT NULL REFERENCES law_versions(id) ON DELETE CASCADE,
  law_id          INTEGER NOT NULL REFERENCES laws(id) ON DELETE CASCADE,
                  -- denormalised from law_versions.law_id: the one-hop answer
                  -- to "which law does this article belong to"
  division_id     INTEGER REFERENCES divisions(id) ON DELETE SET NULL,
  article_key     TEXT NOT NULL,         -- stable across versions: '27', '15-bis', '195-z-1', 'T[03]:primero'
  numero_int      INTEGER,               -- 27      (NULL for ordinal/transitorio articles)
  suffix          TEXT,                  -- 'Bis', 'Ter', 'Z-1', 'Bis 35 A'
  label           TEXT NOT NULL,         -- 'Artículo 27.'
  seq             INTEGER NOT NULL,
  is_transitorio  INTEGER NOT NULL DEFAULT 0,
  decree_group    TEXT,                  -- which TRANSITORIOS block it belongs to
  text            TEXT NOT NULL,         -- full normative text, annotations excluded
  text_sha256     TEXT NOT NULL,
  char_count      INTEGER NOT NULL,
  last_reform_date TEXT,                 -- latest DOF date among its annotations (ISO); NULL = none
  UNIQUE (law_version_id, article_key, seq)
);
CREATE INDEX IF NOT EXISTS ix_art_lv  ON articles(law_version_id, seq);
CREATE INDEX IF NOT EXISTS ix_art_law ON articles(law_id, seq);
CREATE INDEX IF NOT EXISTS ix_art_div ON articles(division_id);
CREATE INDEX IF NOT EXISTS ix_art_key ON articles(article_key);
CREATE INDEX IF NOT EXISTS ix_art_sha ON articles(text_sha256);

-- Párrafos / fracciones / incisos / numerales inside an article.
CREATE TABLE IF NOT EXISTS article_parts (
  id            INTEGER PRIMARY KEY,
  article_id    INTEGER NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  kind          TEXT NOT NULL,           -- parrafo | fraccion | inciso | numeral
  label         TEXT,                    -- 'I', 'a)', '1.'
  seq           INTEGER NOT NULL,
  text          TEXT NOT NULL,
  text_sha256   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_part_art ON article_parts(article_id, seq);

-- Editorial provenance ("Artículo reformado DOF 14-08-2001"). Kept OUT of the
-- normative text on purpose, and attached to whatever it annotates.
CREATE TABLE IF NOT EXISTS annotations (
  id              INTEGER PRIMARY KEY,
  law_version_id  INTEGER NOT NULL REFERENCES law_versions(id) ON DELETE CASCADE,
  article_id      INTEGER REFERENCES articles(id) ON DELETE CASCADE,
  division_id     INTEGER REFERENCES divisions(id) ON DELETE CASCADE,
  seq             INTEGER NOT NULL,
  target_kind     TEXT,                  -- articulo|parrafo|fraccion|inciso|capitulo|...
  action          TEXT,                  -- reformado|adicionado|derogado|recorrido|...
  dof_dates       TEXT,                  -- JSON array of ISO dates
  text            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ann_lv  ON annotations(law_version_id, seq);
CREATE INDEX IF NOT EXISTS ix_ann_art ON annotations(article_id);

-- Lossless landing zone: every converted paragraph with its style features.
CREATE TABLE IF NOT EXISTS blocks (
  id              INTEGER PRIMARY KEY,
  law_version_id  INTEGER NOT NULL REFERENCES law_versions(id) ON DELETE CASCADE,
  seq             INTEGER NOT NULL,
  kind            TEXT NOT NULL,         -- article|article_ordinal|ordinal_lead|heading|transitorio_heading|annotation|note|body|table
  text            TEXT NOT NULL,
  style           TEXT                   -- JSON: css class, size, colour, alignment, bold ratio
);
CREATE INDEX IF NOT EXISTS ix_blk_lv ON blocks(law_version_id, seq);

-- ── change tracking (filled by scripts/diff_versions.py) ───────────────────
CREATE TABLE IF NOT EXISTS version_diffs (
  id                INTEGER PRIMARY KEY,
  law_id            INTEGER NOT NULL REFERENCES laws(id) ON DELETE CASCADE,
  from_version_id   INTEGER NOT NULL REFERENCES law_versions(id) ON DELETE CASCADE,
  to_version_id     INTEGER NOT NULL REFERENCES law_versions(id) ON DELETE CASCADE,
  computed_at       TEXT NOT NULL,
  n_added           INTEGER NOT NULL DEFAULT 0,
  n_removed         INTEGER NOT NULL DEFAULT 0,
  n_modified        INTEGER NOT NULL DEFAULT 0,
  n_unchanged       INTEGER NOT NULL DEFAULT 0,
  UNIQUE (from_version_id, to_version_id)
);

CREATE TABLE IF NOT EXISTS article_changes (
  id                INTEGER PRIMARY KEY,
  version_diff_id   INTEGER NOT NULL REFERENCES version_diffs(id) ON DELETE CASCADE,
  article_key       TEXT NOT NULL,
  change_type       TEXT NOT NULL,       -- added | removed | modified | renumbered | unchanged
  from_article_id   INTEGER REFERENCES articles(id) ON DELETE SET NULL,
  to_article_id     INTEGER REFERENCES articles(id) ON DELETE SET NULL,
  similarity        REAL,                -- 0..1, NULL when added/removed
  diff              TEXT                 -- unified diff for 'modified'; old -> new label for 'renumbered'
);
CREATE INDEX IF NOT EXISTS ix_chg_diff ON article_changes(version_diff_id, change_type);

-- ── citation graph ─────────────────────────────────────────────────────────
-- Statutory cross-references extracted from article bodies: "artículo 27 de
-- esta Ley", "artículo 131 constitucional", "la Ley Aduanera"… The quote is
-- verbatim, so every edge carries its evidence. `resolved` says whether the
-- target article was found in the target law.
CREATE TABLE IF NOT EXISTS cross_references (
  id                INTEGER PRIMARY KEY,
  law_version_id    INTEGER NOT NULL REFERENCES law_versions(id) ON DELETE CASCADE,
  article_id        INTEGER REFERENCES articles(id) ON DELETE CASCADE,
  seq               INTEGER NOT NULL,     -- occurrence order within the article
  quote             TEXT NOT NULL,        -- matched span, verbatim
  ref_kind          TEXT NOT NULL,        -- self-article | constitution | law
  target_law_id     INTEGER REFERENCES laws(id),
  target_article_key TEXT,                -- NULL when the reference is to a whole law
  resolved          INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_xref_lv     ON cross_references(law_version_id);
CREATE INDEX IF NOT EXISTS ix_xref_art    ON cross_references(article_id);
CREATE INDEX IF NOT EXISTS ix_xref_target ON cross_references(target_law_id, target_article_key);

-- ── full-text search (SQLite FTS5) ─────────────────────────────────────────
-- Accent-insensitive: 'importacion' matches 'importación'.
CREATE VIRTUAL TABLE IF NOT EXISTS articles_fts USING fts5(
  label, text, article_key UNINDEXED, law_version_id UNINDEXED,
  content='articles', content_rowid='id', tokenize="unicode61 remove_diacritics 2"
);
CREATE TRIGGER IF NOT EXISTS articles_ai AFTER INSERT ON articles BEGIN
  INSERT INTO articles_fts(rowid,label,text,article_key,law_version_id)
  VALUES (new.id,new.label,new.text,new.article_key,new.law_version_id);
END;
CREATE TRIGGER IF NOT EXISTS articles_ad AFTER DELETE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts,rowid,label,text,article_key,law_version_id)
  VALUES ('delete',old.id,old.label,old.text,old.article_key,old.law_version_id);
END;
CREATE TRIGGER IF NOT EXISTS articles_au AFTER UPDATE ON articles BEGIN
  INSERT INTO articles_fts(articles_fts,rowid,label,text,article_key,law_version_id)
  VALUES ('delete',old.id,old.label,old.text,old.article_key,old.law_version_id);
  INSERT INTO articles_fts(rowid,label,text,article_key,law_version_id)
  VALUES (new.id,new.label,new.text,new.article_key,new.law_version_id);
END;

-- ── views: the one-hop surface for queries, GUIs and BI ────────────────────
-- The normalised truth stays articles -> law_versions -> laws. "Current" is
-- the latest law_version per law (reforma_date desc, id desc).
DROP VIEW IF EXISTS v_laws;
CREATE VIEW v_laws AS
SELECT l.id, l.slug, l.numero, l.nombre, l.nombre_corto, l.codigo_archivo,
       l.tipo, l.estado_vigencia, l.dof_original, l.url_detalle,
       c.jurisdiction, c.slug AS corpus_slug,
       v.id AS law_version_id, v.ultima_reforma, v.reforma_date, v.ultima_reforma_indice, v.source_kind,
       v.captured_at, v.resolved_url, v.source_sha256,
       (SELECT count(*) FROM articles a WHERE a.law_version_id = v.id)    AS article_count,
       (SELECT count(*) FROM divisions d WHERE d.law_version_id = v.id)   AS division_count,
       (SELECT count(*) FROM annotations n WHERE n.law_version_id = v.id) AS annotation_count,
       (SELECT count(*) FROM cross_references x WHERE x.law_version_id = v.id) AS crossref_count
FROM laws l
JOIN corpora c ON c.id = l.corpus_id
JOIN law_versions v ON v.id = (
  SELECT v2.id FROM law_versions v2 WHERE v2.law_id = l.id
  ORDER BY v2.reforma_date DESC, v2.id DESC LIMIT 1);

DROP VIEW IF EXISTS v_articles;
CREATE VIEW v_articles AS
SELECT a.id, a.law_id, l.slug AS law_slug, l.nombre AS law_nombre, l.nombre_corto,
       l.tipo AS law_tipo, c.jurisdiction,
       a.law_version_id, a.article_key, a.numero_int, a.suffix, a.label, a.seq,
       a.is_transitorio, a.decree_group, a.text, a.last_reform_date, a.char_count,
       a.division_id,
       d.kind AS division_kind, d.heading AS division_heading,
       d.rubric AS division_rubric, d.path AS division_path
FROM articles a
JOIN laws l ON l.id = a.law_id
JOIN corpora c ON c.id = l.corpus_id
LEFT JOIN divisions d ON d.id = a.division_id;

DROP VIEW IF EXISTS v_toc;
CREATE VIEW v_toc AS
SELECT d.id AS division_id, d.law_version_id, v.law_id, l.slug AS law_slug,
       d.parent_id, d.kind, d.ordinal_label, d.heading, d.rubric, d.depth, d.seq, d.path,
       (SELECT count(*) FROM articles a WHERE a.division_id = d.id) AS article_count,
       (SELECT count(*) FROM articles a
          JOIN divisions d2 ON d2.id = a.division_id
         WHERE d2.law_version_id = d.law_version_id
           AND d.path IS NOT NULL
           AND (d2.id = d.id OR d2.path = d.path OR d2.path LIKE d.path || '/%')
       ) AS descendant_article_count
FROM divisions d
JOIN law_versions v ON v.id = d.law_version_id
JOIN laws l ON l.id = v.law_id
WHERE d.kind IS NOT 'otro';

DROP VIEW IF EXISTS v_reformas;
CREATE VIEW v_reformas AS
SELECT n.id, n.law_version_id, v.law_id, l.slug AS law_slug, l.nombre_corto,
       n.article_id, a.label AS article_label, a.article_key,
       n.division_id, n.target_kind, n.action, n.dof_dates, n.text, n.seq
FROM annotations n
JOIN law_versions v ON v.id = n.law_version_id
JOIN laws l ON l.id = v.law_id
LEFT JOIN articles a ON a.id = n.article_id;
