# Spike 0003 — Le contexte de Maestro, lisible par un script

Date : 2026-11-22. Claude Code 2.1.330 (macOS), Orca 1.4.259.

## Question

Maestro doit se redémarrer tout seul quand son contexte dépasse un seuil (OPP-78, suite de 0.39.0). Le Monitor, un
script sans LLM, doit donc lire la taille du contexte de la session Maestro. Trois inconnues :

1. Comment un script retrouve-t-il, sans se tromper, le transcript de *cette* session Maestro ?
2. Que valent les champs `usage` des messages du transcript, et que deviennent-ils après `/clear` ou une compaction ?
3. Comment connaître la fenêtre de contexte du modèle (1 M ou 200 k) sans la deviner ?

## 1. Retrouver le transcript de la session Maestro

Un transcript est `~/.claude/projects/<cwd encodé>/<id de session>.jsonl`. Le dossier du projet ne suffit pas : la
session Maestro tourne dans le dossier du clone de Ballet, comme les sessions de développement (ce dossier en contient
des dizaines) ; « le plus récent » prendrait la mauvaise. Il faut l'id de session.

| Piste | Constat |
|---|---|
| `CLAUDE_CODE_SESSION_ID` dans l'environnement de l'outil Bash | présent, égal à l'id du transcript. Vérifié dans la session du desktop, dans un `claude -p` et dans un vrai `claude --remote-control 'spike ctx 0003' '<prompt>'` lancé par `orca terminal create` (comme `ballet_maestro.py maestro`). `CLAUDE_PID` y est aussi (le pid du processus `claude`). |
| après `/clear` (envoyé au terminal Orca) | **nouvelle session** : nouveau fichier, nouvel id ; l'outil Bash voit aussitôt le nouvel id (`CLAUDE_CODE_SESSION_ID` suit). |
| `~/.claude/sessions/<pid>.json` | un fichier par processus `claude` vivant : `sessionId`, `cwd`, `entrypoint`, `name`, `bridgeSessionId`. Son `sessionId` suit aussi `/clear`. Format interne, non documenté. |
| hook `SessionStart` (entrée : `session_id`, `transcript_path`) | documenté et déclenché aussi sur `clear` et compaction, mais il faut un hook dans le plugin qui écrit l'id quelque part : plus de pièces pour le même résultat. |
| transcript le plus récent du dossier | écarté : plusieurs sessions partagent ce dossier. |

**Choix : `claim` note l'id de session dans le bail.** `ballet_maestro.py claim` est lancé par l'outil Bash de la
session Maestro : le script lit lui-même `CLAUDE_CODE_SESSION_ID` (aucun argument à ajouter dans le skill) et le range
sous `[lease] session = "…"`. Pourquoi : c'est la seule piste sans pièce en plus, vérifiée dans le mode de lancement
réel de Maestro, et elle colle à la vie du bail : `release_lease` l'efface, un nouveau Maestro (redémarrage, ou
`/clear` puis `claim --take-over`) note son propre id. Le Monitor retrouve alors le transcript sans connaître le dossier :
`glob("<claude>/projects/*/<id>.jsonl")` (un UUID est unique ; `<claude>` est `CLAUDE_CONFIG_DIR` quand il est posé,
sinon `~/.claude`, ce qui permet aussi d'essayer avec un dossier jetable).

Sans la variable (un `claim` lancé à la main, hors de Claude) : `session` reste vide, le Monitor ne surveille rien et
le dit une fois en ligne d'erreur de son tour. `read_config` ne garde que les clés connues du bail : `session` entre
dans `EMPTY_LEASE`. `sessions/<pid>.json` reste la piste de repli si la variable disparaissait dans une version future.

## 2. La forme de `usage`

Lu sur le vrai transcript de Maestro (session `5d5057ed…`, 82 messages, `claude-opus-5-5`), sur ceux de ce dossier
(5 267 messages de l'assistant) et sur trois sessions d'essai.

- Un message de l'assistant (`"type": "assistant"`) porte `message.model` et `message.usage` :
  `input_tokens` (quelques unités : tout le reste est en cache), `cache_read_input_tokens`,
  `cache_creation_input_tokens`, `output_tokens`, plus des détails (`cache_creation.ephemeral_1h_input_tokens`,
  `iterations[]`, `service_tier`…).
- **Contexte courant = `input_tokens + cache_read_input_tokens + cache_creation_input_tokens` du dernier message
  de l'assistant.** Contrôle : un `claude -p` à deux appels rend 42 510 pour le second (2 + 41 217 + 1 291) ; la
  somme de tout le `usage` du résultat (`-p --output-format json`) est cumulée, donc fausse pour cet usage. La
  sortie du message (`output_tokens`) n'y est pas : elle entre dans l'entrée de l'appel suivant. Le chiffre est celui
  de la dernière requête : un résultat d'outil arrivé depuis n'y est pas encore.
- Maestro aujourd'hui : 135 563 + 2 + 446 = **136 011 tokens** (13,6 % d'1 M) après un jour et demi de travail ; une
  session neuve de cet environnement démarre à ~45 k (système, outils, skills).
- Pièges, mesurés : (a) 4 messages `"model": "<synthetic>"` à usage nul (interruption, erreur) : les ignorer ;
  (b) un message écrit sur plusieurs lignes du fichier (1 850 cas) répète le même `usage` : prendre la dernière ligne
  ou n'importe laquelle ; (c) les sous-agents ont leur propre fichier, pas de ligne `isSidechain` dans le fichier
  principal ici, mais le filtre `isSidechain` ne coûte rien ; (d) un fichier en cours d'écriture peut finir par une ligne
  coupée : lire de la fin et sauter ce qui ne se parse pas.
- **Compaction** (même session, même fichier) : une ligne `{"type":"system","subtype":"compact_boundary",
  "compactMetadata":{"trigger":"auto","preTokens":329231,"postTokens":20675}}`, puis le message suivant retombe
  (328 240 → 89 774 dans l'exemple). Le contexte lu se « remet » donc tout seul : un dépassement qui retombe n'est
  plus un dépassement.
- **`/clear`** : nouveau fichier et nouvel id (voir §1). L'ancien id, tenu par le bail, n'est plus écrit : sans
  nouveau `claim`, le Monitor lirait un transcript figé.
- Observation qui pèse sur le seuil : les 9 compactions automatiques des transcripts de ce dossier ont eu lieu à
  205 k, 252 k, 252 k, 255 k, 259 k, 269 k, 292 k, 312 k et 329 k tokens (preTokens), alors que la fenêtre est d'1 M.
  Un seuil à 30 % (300 k) serait presque toujours devancé par la compaction automatique ; à 20 % (200 k) il
  passe avant. Je n'ai pas trouvé d'où vient ce déclenchement vers 250–330 k (aucun réglage `compact` ni variable
  dans `~/.claude/settings.json`) : à ne pas supposer stable.

## 3. La fenêtre de contexte

- Le transcript ne la dit pas : `message.model` vaut `claude-opus-5-5` (pas de suffixe `[1m]`), les `betas` des lignes
  `api-request` ne contiennent aucun `context-1m…`, et aucun champ `context_window` n'existe dans les fichiers
  (recherché dans tous les transcripts).
- Seul `claude -p --output-format json` la donne : `modelUsage.<modèle>.contextWindow`. Mesuré : **1 000 000** pour
  `claude-opus-5-5`, `claude-sonnet-5-5` et `claude-haiku-5-5` (`claude-fable-5-2` : l'appel a échoué). Mais c'est un
  appel du modèle (jusqu'à 0,25 $ pour « say ok »), pas quelque chose que le Monitor refera toutes les 3 minutes.
- La ligne de statut de Claude Code reçoit `context_window` sur son entrée, mais c'est un réglage de l'utilisateur
  (ici tenu par Orca), pas du plugin : écarté.

**Choix : une clé de configuration, avec la valeur mesurée par défaut.** `[maestro] context_window_tokens`
(1 000 000 sans la clé, entier > 0, validée comme `close_delay_minutes`), qui apparaît dans le corps de l'événement.
Une garde contre l'erreur : un contexte lu supérieur à la fenêtre configurée est une ligne d'erreur du tour (la fenêtre
est fausse), jamais un événement. Pas de table « modèle → fenêtre » dans le code : ce serait deviner pour le
prochain modèle.

## 4. Le chemin du redémarrage (relu, pas modifié)

- **Seulement quand aucun Conductor ne travaille, événement ou non** : `ballet_restart.py when-idle` ne redémarre rien
  lui-même. `request` pose le drapeau de pause et crée le terminal `maestro-restart` ; `run` boucle (30 s) jusqu'à
  `_idle` = aucun Conductor `running` au terminal vivant hors escalade *et* la session Maestro dort sur sa boîte
  (`not is_busy`) ; sinon abandon à 4 h (`maestro · restart abandoned`, drapeau levé). L'événement ne contourne rien :
  il ne fait que *demander*.
- **Un deuxième événement ne redemande pas** : `request` rend `restart already in progress` tant que le terminal
  `[restart]` vit. Et le Monitor n'envoie qu'une fois par session (voir le plan) : double protection. Sans elle, un
  second `DECISION: restart` serait sans effet mais bruyant ; le script de Maestro dira plutôt
  `DECISION: wait (restart already scheduled)` quand `[restart]` est noté.
- Une session Maestro ouverte hors du terminal `maestro` est refusée par `request` (déjà le cas) : le
  `DECISION: restart` est relayé, le refus est dit au Director.

## Ce qui n'est pas vérifié

- Le vrai Maestro du Director n'a pas été touché (ni `claim` ni redémarrage) : `CLAUDE_CODE_SESSION_ID` est vérifié dans
  le même mode de lancement (`claude --remote-control '<nom>' '<prompt>'` dans un terminal Orca), pas dans sa session.
- Les 1 M mesurés valent pour ce compte (Claude Pro) et ces trois modèles ; un autre plan, ou un modèle non mesuré,
  peut avoir une autre fenêtre : d'où la clé.
- Le déclenchement de la compaction automatique vers 250–330 k n'est pas expliqué.
- Les sessions d'essai (Remote Control « spike ctx 0003 ») ont existé quelques minutes côté claude.ai ; leurs
  transcripts locaux sont supprimés, leur terminal fermé.
