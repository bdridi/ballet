# Ballet — releases

Le journal des versions du plugin, la plus récente en haut. Chaque version a son tag git (`vX.Y.Z`), une ligne par fonctionnalité ou changement, et la liste des opportunités qu'elle traite (`opportunities.md`, cochées ✅ là-bas).

## 0.26.0 — 2026-11-19 · `v0.26.0`

- `init-project` prépare, chez le propriétaire du repo GitHub, les types et les champs d'issue de la file : le type `Slice` (à côté de `Task`, `Bug`, `Feature`), les champs `Ballet status`, `Rehearsal mode` et `Priority`. Il ne crée que ce qui manque, ne modifie rien, et signale un champ incomplet ; `--no-github` saute l'étape.
- `ballet_planning.py` relance cette préparation à la main, et dit quel droit manque quand GitHub refuse (`user` pour un compte personnel).
- PRD recentré sur la méthode et réécrit autour des deux boucles (Workshop, Rehearsal), de leurs modes (`assisted`, `autopilot`) et de la file sur GitHub ; `release.md` et `opportunities.md` remplacent `TASKS.md`.

**Opportunités traitées** : OPP-03, en partie (types et champs créés ; la file qui les lit reste à faire).

## 0.25.0 — 2026-11-19 · `v0.25.0`

Première entrée du journal : ce que Ballet sait faire à cette version. Les versions d'avant sont dans l'historique git.

**Plugin et profil**
- Un seul plugin pour Claude Code, Grok et Mistral Vibe, réinstallé depuis le clone par `reset-ballet`.
- Les défauts du plugin (`config.toml`) et le profil du projet (`.ballet/config.toml`) fusionnés clé par clé, vérifiés au lancement : champs projet obligatoires, Critic ≠ Dancer, `needs` sans cycle ni repo inconnu.
- `/ballet:init-project` amorce un projet : profil, `AGENTS.md`, `CLAUDE.md`, lien `.agents/skills`, `.ballet/run/` dans le `.gitignore`.
- Les règles communes en skills : `tdd` (avec la règle de mutation), `bdd`, `ddd`, `clean-code`.

**Les rôles**
- Dramaturg : le backlog (opportunités, retours, bugs, tâches), les capabilities et les features prêtes dans l'espace specs, depuis les modèles `templates/`, dans la langue `[project] specs_language`.
- Choreographer : l'issue et son plan (une section par repo) à partir d'une feature prête, publiés par le script GitHub ; des slices verticales seulement si besoin, le moins possible, chacune sous les deux tiers de `max_diff_lines` ; seul à écrire ADR, spikes et règles techniques d'`AGENTS.md` ; un mode auto sous le Conductor.
- Dancer : sa section du plan en red → green → refactor, un commit vert par tâche, le test rouge cité par tâche ; il demande au Choreographer ou au Dramaturg au lieu d'improviser.
- Critic : un verdict `APPROVED`, `REJECTED` ou `ESCALATE`, tous les points bloquants en un lot, des notes optionnelles ; il vérifie le rouge de chaque tâche et chaque exclusion de mutation.
- Un seul format de message entre rôles (en-tête JSON, corps Markdown), les tours plafonnés par `max_exchange_rounds`.

**La Piece `hybrid-track` et le Conductor**
- `/ballet:hybrid-track` joue une file d'issues ou de features prêtes, une Rehearsal à la fois ; le script ouvre la suivante depuis `main` à la Premiere.
- Une feature (ou une issue sans plan) passe d'abord par une planification, Choreographer seul ; son issue et ses slices prennent la tête de la file, ses ADR partent avec la première slice.
- `--plan review` (défaut) arrête la file jusqu'à `ballet:plan-approved` ; `--plan auto` enchaîne.
- Chaque Rehearsal vit sur sa branche `rehearsal/<ID>`, dans son worktree Orca, et s'intègre par une PR mergée par rebase.
- Toutes les questions, réponses, rapports et verdicts sont publiés sur l'issue et la PR.
- Le script GitHub, liste fermée d'opérations : `read`, `publish`, `plan`, `slice`, `read-pr`, `push`, `open-pr`, `review`, `verdicts`, `resolve`, `comment-issue`, `comment-pr`, `merge`, `label`, `close`.
- La politique déterministe vérifie chaque passage de rôle (périmètre par rôle dans `[policy.roles]`, zones interdites et sensibles, historique, tests de `main` gardés par leur nom) : renvoi une fois, puis escalade.
- La preuve du repo lancée par le script à chaque rapport du Dancer, avant le push ; rouge, le Dancer reprend, au-delà de `max_round_trips` ou de `proof_timeout_seconds`, escalade.
- Le test de mutation après la preuve, sur les lignes changées par la branche : une entrée `[[repos.<repo>.mutation]]` par outil, lancée en arrière-plan, le Conductor réveillé par Orca à sa fin ; rouge, le Dancer reprend avec les survivants ; `[mutation] enabled` et `timeout_seconds`.
- Le rapport de cargo-mutants lu et résumé au journal (tués, survivants, score) ; `ballet_mutation.py run` lance la même mutation à la main.
- La taille du diff comptée par le script (`diff_exclude`), `ballet:oversized` au-delà ; en mode strict, escalade avant le Critic, levée par `ballet:size-accepted`.
- Le verdict en libellé de la PR ; la Premiere exige `ballet:approved` posé après le dernier commit et une CI verte, et attend une CI en cours jusqu'à `ci_wait_seconds`.
- Les notes du Critic prises en un commit, un tour de notes sur un `APPROVED`, une note déclinée avec sa raison.
- Une escalade met la file en pause ; le Director pose son libellé et `resume` reprend la Rehearsal, puis la file ; `status` montre l'état lisible.
- Un worker qui s'arrête sans `worker_done` est relancé une fois.
- La Premiere ferme l'issue, puis sa parente après la dernière slice.
- Le journal `.ballet/run/journal.jsonl` : un événement par passage, message, preuve, mutation, taille, politique, décision.
- La Scène (`ballet_stage.py`) : une page locale en lecture seule, la file, les Rehearsals, le rôle en cours, ce que le Director doit faire, le fil des échanges ; la v2 en aperçu sur `/v2`.

**Opportunités traitées** : aucune, le suivi commence avec cette version.
