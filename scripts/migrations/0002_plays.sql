-- OPP-79, étape 2 : l'état des sessions de Conductor, des Rehearsals et des Workshops de tous les projets.
-- Chaque ligne garde l'état entier en JSON (`data`) ; les colonnes ne sont que ce qu'on cherche ou trie.

CREATE TABLE sessions (
  project    TEXT NOT NULL,   -- l'alias du projet
  item       TEXT NOT NULL,   -- l'élément confié : '#12', 'FEAT-002'
  status     TEXT NOT NULL,   -- open | done
  data       TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (project, item)
);

CREATE TABLE rehearsals (
  project    TEXT NOT NULL,
  id         TEXT NOT NULL,   -- 'FEAT-004.1'
  session    TEXT,            -- l'élément de sa session
  status     TEXT NOT NULL,   -- open | escalated | done
  data       TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (project, id)
);

CREATE TABLE workshops (
  project    TEXT NOT NULL,
  item       TEXT NOT NULL,   -- 'BUG-004', ou le slug d'une demande
  status     TEXT NOT NULL,
  data       TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (project, item)
);

CREATE INDEX nodes_play ON nodes (project, kind, name);
