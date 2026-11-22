-- OPP-79, étape 1 : l'état de Maestro, du Monitor et des Conductors, puis les nœuds du workflow et leurs événements.

-- L'état de la machine, une seule ligne : ce que les scripts créent ou notent en tournant (jamais la config, qui reste
-- dans maestro.toml).
CREATE TABLE runtime (
  one                  INTEGER PRIMARY KEY CHECK (one = 1),
  mailbox_terminal     TEXT,      -- la boîte de Maestro : son terminal Orca
  mailbox_run          TEXT,      -- et la Run créée --from lui
  mailbox_previous_run TEXT,      -- la Run d'une boîte recréée, que recap relit une dernière fois puis oublie
  maestro_terminal     TEXT,      -- où tourne la session Maestro
  monitor_terminal     TEXT,      -- où tourne le Monitor
  restart_terminal     TEXT,      -- le terminal maestro-restart d'un redémarrage en cours
  restart_owns_pause   INTEGER NOT NULL DEFAULT 0,   -- ce redémarrage a posé la pause : il la retire à la fin
  paused_at            TEXT,      -- la pause : plus rien ne part seul (NULL : pas de pause)
  lease_owner          TEXT,      -- le bail de lecture de la boîte : le jeton de la session Maestro
  lease_pid            INTEGER NOT NULL DEFAULT 0,   -- le processus de son attente en cours, 0 sinon
  lease_renewed_at     TEXT,      -- la dernière prise, ou la fin de la dernière attente
  lease_session        TEXT,      -- l'id de la session Claude de Maestro (son transcript)
  context_told_session TEXT       -- la session Maestro dont le Monitor a signalé le contexte au-delà du seuil
);
INSERT INTO runtime (one) VALUES (1);

-- La file des éléments prêts de chaque projet, telle que le dernier tour du Monitor l'a vue.
CREATE TABLE ready (
  project TEXT PRIMARY KEY,         -- l'alias du projet (maestro.toml)
  items   TEXT NOT NULL,            -- JSON : les éléments, dans l'ordre de la file
  seen_at TEXT NOT NULL
);

-- Le registre des Conductors : une ligne par <projet>#<élément>, celle de son dernier Conductor.
CREATE TABLE conductors (
  id            TEXT PRIMARY KEY,   -- 'antimurphy#60'
  project       TEXT NOT NULL,
  item          TEXT NOT NULL,      -- '60', 'FEAT-002', 'BUG-004'
  kind          TEXT CHECK (kind IN ('rehearsal', 'workshop')),   -- NULL : Maestro ne l'a pas lancé
  state         TEXT NOT NULL CHECK (state IN ('running', 'finished', 'gone', 'closed', 'stopped')),
  terminal      TEXT,               -- où tell écrit
  url           TEXT,               -- l'URL Remote Control de sa session
  finished_told INTEGER NOT NULL DEFAULT 0,   -- le Monitor a signalé ce Conductor fini, terminal ouvert
  node          TEXT NOT NULL,      -- son nœud : son lancement, ses annonces, sa fin
  UNIQUE (project, item)
);

-- Les nœuds du workflow : une étape qui commence et finit, jouée par un agent, un script ou le Director.
CREATE TABLE nodes (
  id         TEXT PRIMARY KEY,      -- uuid
  parent     TEXT REFERENCES nodes,
  project    TEXT,                  -- NULL : hors projet (Maestro, le Monitor)
  conductor  TEXT,                  -- '<projet>#<élément>' ; pas de clé étrangère : l'histoire survit au relancement
  kind       TEXT NOT NULL,         -- conductor, rehearsal, workshop, turn, proof, mutation, policy, size, director, merge…
  name       TEXT NOT NULL,
  runner     TEXT NOT NULL CHECK (runner IN ('agent', 'script', 'human')),
  started_at TEXT NOT NULL,
  ended_at   TEXT,                  -- NULL : en cours
  outcome    TEXT CHECK (outcome IN ('ok', 'failed', 'escalated', 'stopped', 'timeout'))
);
CREATE INDEX nodes_running ON nodes (started_at) WHERE ended_at IS NULL;
CREATE INDEX nodes_parent ON nodes (parent);
CREATE INDEX nodes_conductor ON nodes (conductor);

-- Le journal : la même forme pour tout, chaque événement sur un nœud.
CREATE TABLE events (
  id    INTEGER PRIMARY KEY,        -- l'ordre de la machine : le curseur d'un lecteur
  at    TEXT NOT NULL,              -- ISO 8601 UTC
  node  TEXT NOT NULL REFERENCES nodes,
  phase TEXT NOT NULL CHECK (phase IN ('start', 'end', 'mark')),
  kind  TEXT NOT NULL,              -- ce qui s'est passé : launch, escalate, done, message, gone…
  actor TEXT NOT NULL,              -- qui l'écrit : maestro, monitor, conductor, director, dancer…
  data  TEXT NOT NULL DEFAULT '{}'  -- JSON
);
CREATE INDEX events_node ON events (node, id);
CREATE INDEX events_kind ON events (kind, at);
