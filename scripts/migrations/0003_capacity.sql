-- OPP-88 : la sonde de capacité. Une ligne par fenêtre (five_hour, seven_day) dont le Monitor a signalé le franchissement
-- du seuil, tant qu'elle n'est pas redescendue : sa présence est « au-dessus ». Maestro la lit pour sa règle de lancement.
CREATE TABLE capacity_alerts (
  window       TEXT PRIMARY KEY,    -- five_hour | seven_day
  above_since  TEXT NOT NULL,       -- quand le Monitor l'a signalée (ISO 8601 UTC)
  used_percent REAL NOT NULL,       -- le pourcentage utilisé à ce moment
  resets_at    TEXT NOT NULL,       -- le reset de la fenêtre, ISO 8601 UTC ; vide s'il est inconnu
  threshold    INTEGER NOT NULL     -- le seuil franchi
);
