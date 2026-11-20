# Ballet — releases

Le journal des versions du plugin, la plus récente en haut. Chaque version a son tag git (`vX.Y.Z`), une ligne par fonctionnalité ou changement, et la liste des opportunités qu'elle traite (`opportunities.md`, cochées ✅ là-bas).

## 0.31.0 — 2026-11-20 · `v0.31.0`

Le Workshop : `/ballet:workshop` (assisted par défaut, avec l'avis du Choreographer) et `--autopilot`, première partie : une session de Conductor cadre une ligne du backlog sans le Director et publie son issue.

- `/ballet:workshop` est le Workshop, assisted par défaut : une session live avec le Dramaturg (son skill), et l'avis du Choreographer si besoin, sans Conductor ni état. `/ballet:workshop --autopilot <élément>` confie une ligne du backlog (`OPP-12`, `FEAT-007`, `BUG-004`, `TASK-009`) à un Conductor, par un script à part, `ballet_workshop.py` (`begin`, `receive`, `resume`, `status`, la même dernière ligne `NEXT:`). Son état est `.ballet/run/workshop-<élément>.json` et son journal porte la clé `workshop` : ni `session-…` (la Rehearsal), ni clé `id` (la Scène en ferait une Rehearsal). Le Workshop assisted n'a pas de session : c'est `/ballet:dramaturg`.
- Le Dramaturg travaille seul dans un worktree sur `workshop/<élément>` (section « In an autopilot Workshop » de son skill) : il décide dans son périmètre, ne pose pas de question, écrit ses décisions (`## Decided alone`) ou se dit bloqué (`- Blocked:`). À son rapport, le script juge son passage par la politique (seul l'espace specs a bougé ; renvoyé une fois, puis escalade), pousse la branche, ouvre la PR des specs et la merge aussitôt (ni Critic ni CI : des specs ne sont pas du code), puis publie l'issue et range le worktree. Un rapport sans type valide ou sans brouillon est renvoyé une fois. Une reprise (`resume`) repart de l'étape qui a échoué, jamais de celles qui sont faites.
- L'issue sort `proposed` : le Director l'accepte en passant son `Ballet status` à `ready`. Le réglage `[workshop] queue_approval_skipped` du profil (types `Feature`, `Bug`, `Task` ; vide par défaut) la fait sortir `ready` d'emblée pour les types listés (`Queue approval: skipped`).
- Le script GitHub gagne `open-specs-pr` (la PR des specs, liée à aucune issue : celle de la feature naît après son merge) et `merge-specs` (réservée aux branches `workshop/<ID>`, sans verdict de Critic ni CI : des specs ne sont pas du code, et le projet peut ne pas la lancer) ; `push` accepte les branches de Workshop.
- `ballet_orca.py` : les aides Orca des deux Conductors (ouvrir un worktree, lancer un worker, lire la boîte d'Orca) sont sorties de `ballet_rehearsal.py`, sans changer son comportement.
- Le Workshop assisted peut consulter le Choreographer, sans session : le Dramaturg l'appelle une fois, en sous-agent, quand la feature touche un choix technique (dépendance, modèle de données, contrat, plusieurs repos, taille), avec 4 points au plus ; le Choreographer répond ligne par ligne et n'écrit rien (ni plan, ni ADR). Section « Consult the Choreographer » du Dramaturg, section « When consulted during a Workshop » du Choreographer.
- Le Conductor gagne la section « A Workshop session (autopilot) » ; le PRD (§3, §5.4, §6, §11) et le README décrivent le Workshop autopilot et `Queue approval`.

**Opportunités traitées** : OPP-68 (première partie d'OPP-06) ; OPP-05.

## 0.30.1 — 2026-11-19 · `v0.30.1`

Un Dancer refusé pour des fichiers qu'il n'a pas touchés (FEAT-005 sur antimurphy : `AGENTS.md` et l'ADR 0009, commités par le Choreographer).

- La politique juge le Dancer sur ce qu'il a fait : face au `HEAD` qu'il a reçu à sa première mission (`dancer_start`, noté une fois, jamais déplacé aux tours suivants), plus face à l'ouverture du worktree. Les commits du Choreographer et du Dramaturg d'avant ne comptent plus contre lui ; ce qu'il édite lui-même (`AGENTS.md`, un ADR) reste refusé, à chaque tour. Un ancien état sans `dancer_start` se juge comme avant.
- Le Choreographer ou le Dramaturg qui pose une question est vérifié par la politique, et ses commits lui sont notés (`owned`), avant que la question parte : le point de contrôle ne saute plus ses commits quand elle va à l'autre rôle. Un commit hors de son périmètre escalade avant la question.

**Opportunités traitées** : OPP-71.

## 0.30.0 — 2026-11-19 · `v0.30.0`

Le coût d'un run (retour FEAT-004 sur antimurphy : 8 slices, des tours sans travail, la preuve et la mutation en double).

- Le Choreographer découpe par critère, 3 slices au plus, et fait un seul plan par défaut ; la règle des deux tiers disparaît. `max_diff_lines` passe à 1500 par défaut et ne fait que marquer une PR trop grosse pour la review.
- Une approbation avec des notes ne relance plus le Critic : le Dancer les prend en un commit ou les décline ; rien de commité, la Premiere tout de suite ; sinon la politique, la preuve et la mutation, puis `ballet:approved` reposé par le script et la Premiere.
- Le Critic ne relance ni la preuve ni la mutation : sa consigne dit le commit où le script les a passées. Une preuve déjà verte sur le même commit ne repasse pas (`proof-reused`).
- La mutation ne porte que sur ce qui a changé depuis la dernière mutation verte ; sans `paths`, une entrée `cargo-mutants` ne retient que le Rust (`*.rs`). Un outil vert qui n'a testé aucun mutant viable (FEAT-004.3 : 8 mutants, tous invalides, lu « 0 killed, 0 survived ») se signale, `mutation inconclusive`, sans bloquer.
- Le script refuse un rapport du Dancer dont une tâche cochée n'a pas sa ligne `Red:`, avant de rien lancer ; la seconde fois, escalade. Pour le Critic, un rouge qui n'est pas le bon devient une note.
- Une question adressée au Conductor va au Director au lieu de faire planter le script (`KeyError: 'conductor'`).
- La politique juge le Dancer face au point de départ de sa branche (le `HEAD` du worktree à son ouverture), plus face à `origin/main` : un commit de `main` pas encore poussé ne lui est plus attribué.
- Un test renommé que le Dancer déclare dans son rapport (`- Renamed test: <ancien> → <nouveau>`) n'est plus une violation.

**Opportunités traitées** : OPP-14, OPP-18, OPP-25, OPP-60, OPP-61, OPP-62, OPP-63, OPP-64, OPP-65.

## 0.29.0 — 2026-11-19 · `v0.29.0`

- En `assisted`, le plan attend la review du Director par défaut. Le champ d'issue `Plan approval` (`required`, `skipped`) l'emporte, sinon `[rehearsal] plan_approval` du profil (`true` par défaut, écrit par `init-project`) ; une feature sans issue suit le profil, l'`autopilot` n'attend jamais. Le début de session dit ce qui est retenu et d'où (`plan approval required (issue)`).
- La review du plan est une discussion avec le Choreographer, par le Conductor : le Director lui envoie un message `question` (il répond sans toucher au plan), `revise` (il amende le plan et ses slices, puis refait son rapport) ou `approve` (le Dancer part). Chaque échange est publié sur l'issue planifiée ; `Ballet status` reste `plan-review` jusqu'à `approve`. Deux types de message s'ajoutent, `revise` et `approve`, réservés au Director.
- Un plan amendé remplace les slices de la session par celles de sa nouvelle version.
- Le libellé `ballet:plan-approved` disparaît, avec `ask_plan_approval` et `plan_approved` de `ballet_github.py` ; `resume` n'approuve plus un plan.
- `Rehearsal mode` ne garde que `assisted` et `autopilot` : `assisted + plan approval` est refusée comme un mode inconnu. `init-project` crée le champ `Plan approval`.
- La Scène dit au Director de répondre au Choreographer par le Conductor.

**Opportunités traitées** : OPP-57, OPP-19 ; OPP-07, OPP-08 et OPP-46 en partie. Nouvelles : OPP-58 (retirer une slice dans un `revise`), OPP-59 (la review du plan sans le Conductor ouvert).

## 0.28.0 — 2026-11-19 · `v0.28.0`

- `/ballet:rehearsal #12` (ou `FEAT-002`) remplace `/ballet:hybrid-track` : il confie un seul élément, une `Feature`, un `Bug` ou une `Task`, à un Conductor, qui le joue jusqu'à sa dernière Premiere. Le script l'ouvre par `begin <élément>` ; `run`, la liste d'éléments et `--plan` disparaissent.
- Une session par élément à la place de la file du projet (`.ballet/run/session-12.json`, `session-FEAT-002.json`) : l'élément, son issue, ses slices dans l'ordre du plan, la Rehearsal en cours, ce qui est joué et le mode. Deux sessions tournent côte à côte ; un élément déjà en session est refusé, par sa feature comme par son issue. Une `Slice`, ou une issue sans type, n'ouvre pas de session.
- Le mode se lit sur le champ `Rehearsal mode` de l'issue (vide : `assisted`) : seul `assisted + plan approval` arrête sur le plan, avec le libellé `ballet:plan-approved` comme avant. `[escalation] plan_approval` disparaît du profil : par défaut, le plan enchaîne.
- Le script écrit le champ `Ballet status` de l'issue quand il change : `in-rehearsal` tant que la session joue, `plan-review` quand le plan attend le Director, `escalated` à une escalade, `done` à la dernière Premiere. Un refus de GitHub se dit sans rien arrêter. `ballet_github.py` gagne `set_status` et `queue_fields`.
- Sans `<ID>`, `receive`, `premiere`, `resume` et `status` visent la seule session ouverte, et refusent s'il y en a plusieurs ; `resume` et `status` prennent aussi l'élément d'une session (`resume #12`).
- La Scène lit toutes les sessions ouvertes, avec leur mode.
- Correctif : une issue dont le corps commence par `## Plan` ne fait plus tomber le script.

**Opportunités traitées** : OPP-55 ; OPP-08 en partie. Nouvelle : OPP-57 (comment le Director approuve un plan).

## 0.27.0 — 2026-11-19 · `v0.27.0`

- `ballet_program.py` lit le programme sur GitHub : les issues ouvertes `Feature`, `Bug` et `Task` dont `Ballet status` vaut `ready`, dans l'ordre du champ `Priority` puis de l'ancienneté ; les `Slice` n'y figurent pas. Lecture seule, avec un message clair si GitHub ne répond pas.
- La Scène (v1 et v2) montre ce programme, relu toutes les 30 secondes (« programme indisponible » si `gh` échoue). Les sessions de Conductor ouvertes (aujourd'hui `queue.json`, une seule, prête pour plusieurs) sont montrées à part, chacune avec son élément confié, ses slices qui restent et sa Rehearsal courante ; le programme n'a plus les éléments qu'une session a pris ; l'historique joué vient des événements `begin` du journal, la Rehearsal courante des états. Tant que le Conductor n'a qu'une file globale (OPP-55), `run #12 #14` y montre #14 comme une slice de #12.
- Le Dramaturg publie l'issue d'une feature prête (ou d'un bug, d'une tâche) par `ballet_github.py publish <fichier> <type> <statut>` : type natif `Feature`, `Bug` ou `Task`, champ `Ballet status` à `ready` après le oui du Director (`proposed` en autopilot). Sans plan : le script ajoute une section `## Plan` vide.
- Le Choreographer n'écrit plus que le plan sur cette issue (`plan`) et crée les slices, de type `Slice` et sans statut (`slice`). Une feature qui n'existe que dans les specs (sans issue) reste planifiable : il la publie alors à `in-rehearsal`.
- Le plan de chaque slice se suffit à lui-même (ses décisions, sa preuve, ses tâches, ce qu'il reprend des slices d'avant) : le Dancer ne lit que l'issue de sa slice.
- Type ou champ absent : l'opération le dit et renvoie vers `init-project`, et si le champ est refusé après la création, l'erreur nomme l'issue créée.

**Opportunités traitées** : OPP-03, OPP-56.

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
