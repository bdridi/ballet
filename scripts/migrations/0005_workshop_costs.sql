-- OPP-95 : le coût des Workshops assisted, lu par le Monitor dans les notes `ballet:cost` des issues (`ballet_workshop_costs.py`).
-- Une ligne par tranche d'une session Claude Code : la part de la session entre deux `publish`. La Scène ne lit que ces tables.
CREATE TABLE workshop_costs (
  project    TEXT NOT NULL,       -- l'alias du projet dans maestro.toml
  session    TEXT NOT NULL,       -- l'id de la session Claude Code du Workshop
  segment    INTEGER NOT NULL,    -- 1 pour la première issue publiée par la session, puis 2, 3…
  issue      INTEGER NOT NULL,    -- l'issue qui porte la note
  title      TEXT NOT NULL,       -- son titre, lu avec la note
  started_at TEXT NOT NULL,       -- le début de la tranche (ISO 8601)
  ended_at   TEXT NOT NULL,       -- sa fin : le `publish`
  tokens     TEXT NOT NULL,       -- JSON : par modèle, input, output, cache_write_5m, cache_write_1h, cache_read
  usd        REAL NOT NULL,       -- l'équivalent au prix de l'API
  PRIMARY KEY (project, session, segment)
);
-- Une note `ballet:cost` que `parse_cost_note` n'a pas pu lire : gardée pour être dite, jamais un arrêt du tour.
CREATE TABLE workshop_cost_problems (
  project TEXT NOT NULL,
  comment TEXT NOT NULL,          -- l'id GitHub du commentaire : le relire ne la double pas
  issue   INTEGER NOT NULL,
  title   TEXT NOT NULL,
  problem TEXT NOT NULL,          -- `format v2` (une version inconnue) ou `malformed`
  PRIMARY KEY (project, comment)
);
-- Jusqu'où le Monitor a lu les issues de chaque projet : la date de mise à jour de la dernière issue rangée.
CREATE TABLE workshop_cost_watermarks (
  project       TEXT PRIMARY KEY,
  updated_since TEXT NOT NULL     -- ISO 8601 UTC ; le tour suivant relit à partir d'elle (incluse : relire est sans effet)
);
