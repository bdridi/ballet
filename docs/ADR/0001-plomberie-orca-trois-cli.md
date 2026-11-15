# ADR 0001 — Plomberie Orca avec Claude, Grok et Mistral Vibe

- Statut : acceptée
- Date : 2026-11-14
- Source : spike 1 (PRD §15.1), branche `spike/01-plomberie`, commits `6836078` à `20d465f`, note détaillée `spikes/01-plomberie.md` sur cette branche.

## Contexte

Le PRD suppose qu'un worker Orca lancé avec n'importe lequel des trois CLI reçoit une spec, voit les skills, sait appeler `ask` et `worker_done`, et accepte des permissions imposées. Le spike l'a vérifié sur une tâche bidon.

## Constats

- **Claude** : tout fonctionne (skill natif, `ask`, `worker_done`).
- **Grok** : `ask` et `worker_done` fonctionnent. Le skill projet n'est pas vu nativement (hypothèse : dossier non approuvé, non vérifiée). `--deny "Bash(gh:*)"` est vérifié.
- **Mistral Vibe** : tout fonctionne (skill natif via `.agents/skills`, `ask`, `worker_done`) après authentification. Orca n'a pas de session structurée pour lui (terminal agent). Il demande une approbation de dossier interactive au premier lancement. Une première tentative, avant authentification, a échoué (prompt collé dans zsh, erreur « Invalid API key » trompeuse) ; sa cause exacte n'est pas établie.

- **Permissions** (vérifiées sur disque) : lecture seule, limite au dossier et privation de `gh` sont imposables sur Claude et Vibe. Sur Grok, la lecture seule et le refus de `gh` tiennent ; la limite au dossier ne tient que par une règle `--deny Write(chemin)` (le bac à sable `--sandbox workspace` n'a rien bloqué, test sous `/tmp` non concluant) ; la privation du jeton par l'environnement n'a pas pu être testée (limite d'usage gratuit de Grok atteinte).
- **Jeton GitHub** : les CLI transmettent l'environnement du lancement à leur shell. Il faut retirer `GH_TOKEN` / `GITHUB_TOKEN` **et** pointer `GH_CONFIG_DIR` vers un dossier vide (`gh` est aussi connecté par le trousseau macOS).
- **Vibe en terminal dans Orca** : la liste des agents à session structurée est codée en dur dans Orca ; Vibe n'y figure pas (`vibe-acp` existe pourtant).

## Décision

1. La méthode du PRD tient pour Claude et Grok : on garde les workers Orca et la communication en étoile via `ask` / `worker_done`.
2. Les trois CLI sont utilisables comme workers. Le Dancer démarre sur Claude (référence du PRD §9), puis Mistral à l'étape 4.
3. Le lien `.agents/skills` → `.claude/skills` est retenu pour Vibe (vérifié).
4. **Permissions : on n'impose rien pour l'instant.** Les workers suivent des consignes dans leur spec (lecture seule, dossier de travail, pas de `gh`, pas de jeton) et le **Conductor vérifie le diff** de chaque worker avant d'aller plus loin. L'imposition par le CLI est reportée à un spike 1 bis (`TASKS.md`). Pistes déjà vérifiées pour ce spike : règles de refus (`--deny`, `--disallowedTools`, `denylist`) et environnement purgé (`GH_TOKEN`, `GITHUB_TOKEN` retirés, `GH_CONFIG_DIR` vide) ; détails dans `spikes/01-plomberie.md`.
5. Si on impose Vibe plus tard : jamais `--agent auto-approve` pour un rôle contraint, il écrase la config.

## Conséquences

- `init-project` doit pré-approuver le dossier de confiance de Vibe (et vérifier celui de Grok), sinon un worker non interactif reste bloqué.
- Le Conductor doit traiter Vibe comme un worker en mode terminal (autre cycle de vie que Claude et Grok) et vérifier son lancement.
- À l'étape 2, tester le skill via le plugin (le spike n'a testé que des skills projet) et l'approbation de dossier côté Grok.
- Spike 1 bis : privation du jeton et limite au dossier pour Grok, passage de l'environnement par Orca.
- Le PRD §17 est mis à jour sur : visibilité des skills par Vibe, lien `.agents/skills`, permissions par CLI (partielles).
