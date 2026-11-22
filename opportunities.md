# Ballet — opportunités

Ce qui reste à faire, à vérifier ou à trancher dans Ballet. La méthode est dans `PRD.md`, ce qui est livré dans `release.md`.

- 🆕 à traiter. Un sujet traité sort d'ici : sa version et son numéro sont dans `release.md`.
- Un sujet garde son numéro pour toujours, même sorti d'ici. Pas de doublon : un nouveau besoin proche d'un sujet existant l'enrichit.
- Dans chaque section, du plus pressé au plus lointain.

## La vision

- **La file, c'est GitHub.** Une issue a un type (`task`, `bug`, `feature`, `slice`) et un statut ; une `task`, un `bug` ou une `feature` au statut prêt attend sa Rehearsal. Les slices naissent de la planification d'une feature et se jouent à sa suite.
- **Un observateur déterministe** (un script, pas un agent : le Monitor) surveille la file et signale l'élément prêt ; il ne lance rien. C'est Maestro qui lance une session de Conductor neuve, seul pour ce que le projet confie à l'auto, sinon sur le oui du Director. L'état vit dans les scripts et sur GitHub : rien à garder en mémoire d'une session à l'autre.
- **Chaque boucle tourne en `assisted` par défaut**, ou en `autopilot` quand on la lance ainsi.
- **Le Workshop sort une feature prête, jamais un plan.** Le Choreographer y donne son avis technique tôt, parce qu'il peut changer le choix produit. En assisted, le Director, le Dramaturg et le Choreographer ; en autopilot, le Dramaturg et le Choreographer seuls, et la feature sort proposée, prête une fois que le Director l'accepte ; le full autopilot (prête d'emblée) reste une option.
- **La Rehearsal planifie sur le vrai `main`** : le Choreographer commence par le plan, juste avant le Dancer, pour qu'il ne se périme pas. En assisted, elle escalade vers le Director ; en autopilot, c'est le mode nuit.
- **En autopilot, chacun décide dans son périmètre** : le Dramaturg tranche le métier ; le Choreographer l'architecture, et demande le métier au Dramaturg ; le Dancer suit l'architecture, et demande au Choreographer. Ce qui est décidé sans le Director est marqué et réuni dans un rapport du matin ; il ne reçoit en direct que ce qui sort de tous les périmètres.
- **Un budget** borne ce que l'autopilot dépense.
- **Maestro**, le point d'entrée du Director pour plusieurs projets, et le seul à lancer les Conductors (livré, 0.33.0 à 0.39.0).

## Les deux boucles et la file

- 🆕 **OPP-74 · Installer Ballet sur un poste** (`/ballet:setup` ; lié à Maestro) : un skill qui prépare une machine, une fois, en mode **présentiel** ou **headless**. Il vérifie les outils (`git`, Python, `gh` authentifié avec les bons scopes, Claude Code, la CLI Orca), installe le plugin (`reset_plugin.py`), crée `~/.ballet/` (la config `maestro.toml` ; plus tard la base SQLite), enregistre les projets (alias, chemin, `orca repo add`) et passe chacun par `/ballet:init-project` s'il ne l'a pas (profil, types d'issues, champs et labels GitHub), vérifie la connexion à GitHub, crée la boîte de Maestro, lance le premier Monitor et le premier Maestro. En headless seulement : le service `orca serve --supervise` et celui du gardien (systemd), qui crée et garde la boîte, le Monitor et Maestro. **Le présentiel est livré** : `/ballet:setup` (0.33.0 : outils, `reset_plugin.py`, projets, `/ballet:init-project` proposé, la boîte), le terminal du Monitor (0.36.0), la session Maestro (0.36.0), la clé `[conductors] close_finished_after_minutes` (0.38.0). **Reste tout le headless** : Linux et systemd (refaire le spike 0001, `docs/spikes/0001-superviseur-boite-orca.md`), `orca serve --supervise`, le gardien. **Le gardien `ballet_keeper.py`** (nom à trouver ; sans LLM, hors d'Orca) garde vivants les trois terminaux Orca de l'ensemble : la boîte, le Monitor et Maestro. Une boucle : chacun existe-t-il, répond-il ? Sinon il le recrée (`orca terminal create --command …`, qui marche sans handle), note le nouveau handle dans `~/.ballet/maestro.toml` et le dit dans la boîte (« Maestro relancé »). Il tourne sous systemd (launchd sur le Mac), après `orca serve`, et ne lance aucun Conductor. La boîte recréée : la nouvelle Run est notée, l'ancienne relue une dernière fois par Maestro. Le redémarrage de Maestro (`ballet_restart.py`, 0.39.0) crée déjà son terminal par `ballet_maestro.py maestro` : le gardien réutilise ce chemin. **Fini quand** une machine neuve passe, par ce seul skill, à un Maestro qui répond à `status` et qu'un élément passé `ready` sur un projet de test réveille.
- 🆕 **OPP-75 · Le Conductor figé** (lié à OPP-01) : le Monitor ne voit qu'un Conductor dont le terminal a disparu. Un Conductor dont le terminal vit mais qui ne fait plus rien (bloqué sur une demande de permission, un outil qui ne répond plus, une session Claude plantée) n'envoie rien : Maestro ne le sait pas. À trouver : un signal sans LLM (le dernier changement de la session ou du journal `.ballet/run/` du projet, le terminal qui n'affiche plus rien depuis un délai) et une réponse (le dire à Maestro, qui prévient le Director, qui peut alors l'arrêter : `ballet_launch.py stop`, 0.39.0).
- 🆕 **OPP-79 · L'état en SQLite** (lié à Maestro et à son registre ; avant de revoir la Scène) : un état au niveau de l'utilisateur, `~/.ballet/ballet.db` (`sqlite3` de la bibliothèque standard), qui n'est pas le canal (le canal reste la boîte Orca). Il tient les projets (alias, chemin), le registre des Conductors (une table `conductors`, qui remplace `conductors.json` ; les écritures concurrentes en WAL), et l'historique de tous les projets, rangé par projet (colonne `project`), que la Scène lit en un seul endroit. À faire : le schéma, la migration des `journal.jsonl`, l'écriture concurrente, les scripts qui écrivent ou lisent le journal (Rehearsal, Workshop, mutation détachée, frictions, Scène). Règle au passage le format du journal (OPP-36), la lenteur de la Scène (OPP-73) et le verrou du journal d'OPP-49 ; la Scène est revue ensuite (OPP-43, OPP-44, OPP-45, OPP-69).
- 🆕 **OPP-69 · Le Workshop autopilot sur la Scène** : afficher les sessions de Workshop autopilot, les issues `proposed` qui attendent le oui du Director et leurs décisions prises seul (`ballet:decided-alone`). À reprendre dans la Scène revue après la base (OPP-79).
- 🆕 **OPP-07 · Rehearsal assisted ou autopilot** (en partie, 0.29.0 : l'assisted et la review du plan) : le Choreographer planifie au début, sur le vrai `main` (une issue qui a déjà son plan va droit au Dancer) ; assisted, le Director reçoit les escalades et le plan attend sa review, sauf si le champ `Plan approval` de l'issue ou le profil la saute ; autopilot, le mode nuit, le Director hors de la boucle, les décisions prises par périmètre. **Aujourd'hui, l'autopilot ne fait que sauter l'approbation du plan.** Reste : chaque rôle tranche dans son périmètre (le Choreographer demande le métier au Dramaturg, plus au Director), ce qui est décidé seul est marqué `ballet:decided-alone` sur l'issue ou la PR, comme au Workshop, et entre au rapport du matin (OPP-52).
- 🆕 **OPP-52 · Le rapport du matin** : ce que la nuit a mergé, escaladé, et décidé sans le Director (ADR, specs, rapports), de quoi relire en quelques minutes.
- 🆕 **OPP-53 · Le budget de l'autopilot** : un plafond (par nuit, par projet ; en tokens, en temps ou en Rehearsals, à affiner) ; atteint, l'observateur n'ouvre plus rien et le dit.

## Mutation : trous connus

- 🆕 **OPP-12 · Reprendre après une escalade avant la PR** : mutation rouge au-delà de `max_round_trips`, trop longue, en panne, ou worktree qui a bougé ; même trou pour la preuve. `resume` répond « no pull request yet ». Donner au Director un moyen de trancher : relancer, passer, ou renvoyer au Dancer.
- 🆕 **OPP-13 · Un réveil perdu** : si le message Orca ne part pas (`mutation-wake` avec `sent: false`), le Conductor attend sans le savoir. `receive --mutation` rattrape, encore faut-il y penser. Pistes : `status` signale une mutation finie mais non reçue, ou la Scène le montre.
- 🆕 **OPP-15 · La politique signale les changements du `config` de l'outil** (les exclusions), pour que le Critic ne les rate pas.
- 🆕 **OPP-16 · Les recettes par stack dans `init-project`** : l'entrée `mutation` toute prête pour Rust (cargo-mutants `--in-diff {diff}`), TS (StrykerJS `--mutate {ranges}`), JVM (PIT).
- 🆕 **OPP-17 · Les lecteurs `stryker` et `pit`** dans `ballet_mutation.py`, chacun vérifié sur un vrai rapport (fixture dans `tests/fixtures/`). Le front d'antimurphy attend les contournements du pilote : TypeScript 7, pnpm, le bac à sable de Stryker.

## Coût d'un run (retour FEAT-004, antimurphy)

Trop cher pour la valeur : chaque slice et chaque tour paient un coût fixe (Dancer et Critic qui relisent le code, worktree, PR, preuve avec e2e, mutation, attente de la CI). Déjà traités : OPP-14, 18, 25, 60 à 65, 71, 72 (`release.md`).

- 🆕 **OPP-77 · Une feature coûte ~4 à 5 $** (prix API, mesuré sur FEAT-007 et FEAT-008 d'antimurphy, hors Workshop, Maestro et Monitor) : Choreographer (Opus) ~1,3-1,5 $, Dancer (Sonnet) ~1,4-1,7 $ pour 60 tours, Critic (Opus) ~0,5 $, Conductor (Opus) ~0,8-1 $. Le poste dominant est la relecture du contexte à chaque tour (Dancer de FEAT-007 : 63 tours × ~130 k = 8,1 M tokens relus pour 45 k écrits) : le coût croît comme le carré de la longueur d'une session. Ce qui remplit le contexte : un socle fixe d'~46 k tokens par worker (prompt système, outils dont les MCP du poste, plugins, AGENTS.md, skill), des fichiers lus en entier, la spec relue en plus du plan, le Dancer qui relit ses commits (`git show`), le Critic qui lit tout le profil (24 k caractères) et le diff complet (39 k). Leviers, du plus rentable au moins rentable : 1. des sessions courtes (un Dancer par tâche ou petit groupe, qui ne reçoit que sa section du plan) ; 2. un socle allégé (workers lancés sans MCP ni plugins inutiles, `--strict-mcp-config`, seul le skill du rôle ; mesurer d'abord les 46 k) ; 3. des scripts qui résument (la section utile du profil pour le Critic, `diff --stat` puis fichiers ciblés, `git log --oneline`) ; 4. des lectures ciblées dans les skills ; 5. les modèles (Conductor sur Sonnet ou Haiku, Choreographer sur Sonnet pour les petites features) ; 6. moins de tours (outils en parallèle, effort plus bas pour le Dancer). Plus tard, le coût d'une Rehearsal dans ses frictions (0.38.0).
- 🆕 **OPP-78 · Maestro reste un relais** (lié à OPP-77) : le 21/11, la session Maestro a servi à l'analyse de coût (scripts, profils de sessions, skill `claude-api`) ; sa fenêtre s'est remplie en deux features, et chaque réveil la relit. Les analyses se font dans une autre session (le skill Maestro le dit et le refuse) ; Maestro est lancé avec le même socle allégé que les workers (OPP-77, levier 2).
- 🆕 **OPP-66 · Garder le Dancer d'une slice à l'autre d'un même élément** : il ne réexplore plus le code à chaque slice (le contexte relu est servi par le cache des prompts). Risque : un contexte long qui mélange les slices ou garde du code périmé. Session neuve au-delà d'un seuil de tokens, avec un résumé de la slice précédente. Le Critic reste neuf à chaque slice. À mesurer une fois OPP-25 en place.
- 🆕 **OPP-67 · Une seule preuve complète avant le merge** : la preuve (e2e compris) passe par le script à chaque tour, puis la CI la refait avant le merge. Trancher : une preuve rapide par tour et la complète une fois, ou faire confiance à la CI.

- 🆕 **OPP-80 · Reprendre un Conductor arrêté** (lié à `ballet_launch.py stop`, 0.39.0) : `stop` ferme le terminal et les workers, passe la Rehearsal (ou le Workshop) à `escalated` et le `Ballet status` à `escalated`, et garde l'état, la branche, le worktree et la PR. Mais rien ne reprend : une session ouverte refuse un nouveau lancement (`ballet_launch.py`) et `begin` (« already played by the session »). Il faut qu'un Conductor lancé sur l'élément reprenne en plein vol : rouvrir la Rehearsal, savoir quel rôle tenait la main (les `dispatches` gardés disent lesquels étaient lancés, pas lequel travaillait), relancer ce rôle dans le worktree avec sa mission, et un `ballet_launch.py resume <projet> <élément>` côté Maestro. Aujourd'hui `resume` ne sait que traiter une décision du Director sur la PR. **Fini quand** un élément arrêté en plein Dancer repart, depuis son worktree, sans rien refaire de ce qui était commité.

## Rehearsal et file

- 🆕 **OPP-20 · Une feature déjà planifiée relancée** (`/ballet:rehearsal FEAT-002` une seconde fois) : le Choreographer recréerait son issue. Chercher l'issue existante avant d'ouvrir la planification, et jouer ses slices ouvertes.
- 🆕 **OPP-21 · Une parente dans la file** (`/ballet:rehearsal #13`) : sans tâches propres, elle repart en planification. Une parente qui a des slices ouvertes se déroule en ses slices, dans l'ordre.
- 🆕 **OPP-22 · Compter les tours par point, pas par issue** : au premier run, 3 questions sur 3 sujets différents auraient escaladé à tort. Trancher : un sujet par point (`#2/wasm-outdir`) ou `round` remis à 1 sur une nouvelle question.
- 🆕 **OPP-23 · Les notes déclinées adressées au Choreographer** (amender une décision, fixer un contrat pour la slice suivante) se perdent dans la PR au merge. Les lui porter, ou les reporter sur la parente ou la slice suivante.
- 🆕 **OPP-24 · Une troisième catégorie du Critic**, à côté des points bloquants et des notes : opportunité, vigilance, bug hors du diff, versée au backlog du Dramaturg. Circuit à définir.
- 🆕 **OPP-58 · Retirer une slice dans un `revise`** : le Choreographer peut réécrire ou ajouter une slice, pas en fermer une ; il le dit dans son rapport et le Director la ferme à la main avant d'approuver. Une opération du script GitHub (fermer une slice du plan, avec sa raison) le ferait dans sa session.
- 🆕 **OPP-59 · La review du plan sans le Conductor ouvert** : aujourd'hui elle passe par la session du Conductor. Quand l'observateur (OPP-01) lancera les sessions, le Director devra pouvoir répondre depuis GitHub (un commentaire sur l'issue relayé au Choreographer, `Ballet status` repassé à `in-rehearsal` pour approuver), avec un veilleur qui réveille le Conductor, comme la mutation.
- 🆕 **OPP-26 · Le Choreographer vérifie l'outillage** dont dépend son plan (version, comportement) par un spike, plutôt que de reprendre `AGENTS.md` (cas : isolation D1 de `@cloudflare/vitest-plugin` 1.8.2).
- 🆕 **OPP-28 · Les sous-issues natives de GitHub** plutôt que la ligne `Part of #N` et la recherche (avancement visible sur la parente).

## Politique et GitHub

- 🆕 **OPP-29 · L'état GitHub de l'issue et de la PR inchangé** pendant le passage d'un rôle (sauf le Choreographer sur son issue et ses slices).
- 🆕 **OPP-30 · Un commit appartient au rôle du passage où il est apparu** : le Conductor relève l'état du repo à chaque relais ; au `ask` du Dancer, l'arbre non commité est vérifié ; au retour du Choreographer, l'arbre non commité est inchangé ; un registre sha → rôle hors du worktree, vérifié avant la Premiere. Limite : tient tant que le Dancer ne peut pas écrire dans le dossier du Conductor (voir la signature par rôle, PRD §17).
- 🆕 **OPP-31 · Le Choreographer a son propre worktree pour ses spikes** quand il répond au Dancer : aujourd'hui son `checkout` passe par-dessus le travail en cours du Dancer.
- 🆕 **OPP-32 · Le Dramaturg en Workshop** (sur `main`, hors Conductor) n'est pas vérifié par la politique.
- 🆕 **OPP-33 · Un test existant dont le corps change** (une attente affaiblie) : aujourd'hui, seul le Critic le voit.
- 🆕 **OPP-34 · Chaque violation du PRD §5.3 couverte par un test**, sur des repos jouets.
- 🆕 **OPP-35 · Le script GitHub, opérations manquantes** : cocher une tâche du plan, journaliser chaque appel (opération, entrées, résultat).
- 🆕 **OPP-36 · Figer le format du journal** (`.ballet/run/journal.jsonl` : `at`, `rehearsal`, `event`, `detail`). Se règle avec la base (OPP-79).

## Rôles et règles

- 🆕 **OPP-37 · Les règles communes chargées par chaque rôle** : tdd et clean code partout (déjà chargées par le Dancer et le Critic), et une règle trunk-based qui n'existe pas encore.
- 🆕 **OPP-38 · Ajuster les rôles et les seuils sur les runs réels** : lire le journal (refus du Critic, allers-retours, builds rouges, merges à corriger après coup), jusqu'à un avis chiffré sur la qualité du Critic.
- 🆕 **OPP-39 · Le Dramaturg : parcours, flux et expérience** (le `/storyboard` de flownest).
- 🆕 **OPP-40 · Partager les skills user de Claude avec Vibe** (lien `~/.vibe/skills` → `~/.claude/skills`), une fois le ménage des skills user fait.

## CLI et modèles

- 🆕 **OPP-41 · Grok** : vérifier `/ballet:dramaturg`, le priver du jeton GitHub par l'environnement du lancement, le limiter au dossier de travail (`--sandbox workspace` n'a rien bloqué sous `/tmp`). Bloqué par la limite d'usage gratuit.
- 🆕 **OPP-42 · Dancer Claude puis Dancer Mistral** sur les mêmes issues, et comparaison (PRD §9) ; Mistral Vibe lancé par le Conductor.

## La Scène

La Scène sera revue après la base (OPP-79), qui change ce qu'elle lit.

- 🆕 **OPP-43 · Finir la Scène v2** (`stage/v2.html`, servie sur `/v2`) et retirer la v1 une fois l'usage éprouvé.
- 🆕 **OPP-44 · La mutation sur la Scène** : `mutation-start`, `mutation-end`, `mutation-skipped` et `mutation-wake` au fil, avec le score et les survivants, et « mutation running » dans la phase.
- 🆕 **OPP-45 · La Scène, ensuite** : valider le nom au vocabulaire (PRD §3), les temps par phase, la comparaison des modèles, un registre de projets.
- 🆕 **OPP-73 · La Scène lente au démarrage** : mesuré sur antimurphy, un instantané prend ~20 s, dont 16 s pour les titres (24 `gh issue view` l'un après l'autre, gardés en mémoire ensuite) ; le journal se lit en 16 ms. Et chaque changement renvoie tout le journal à la page (332 Ko sur 359). À faire : les titres en un seul appel (`gh issue list --json number,title`) ou écrits dans l'état au `begin` ; n'envoyer à la page que les entrées nouvelles du journal. Se règle avec la base (OPP-79).

## Profil

- 🆕 **OPP-46 · Ranger le profil** (en partie, 0.29.0 : `plan_approval` dans `[rehearsal]`) : une table par étape (`[proof] timeout_seconds` au lieu de `[escalation] proof_timeout_seconds`, comme `[mutation]`) ; `plan_approval`, choix de workflow, hors de `[escalation]`, qui ne garde que les seuils qui font remonter au Director. Casse les profils existants : migration par `init-project`.

## Plus loin

- 🆕 **OPP-47 · Projet multi-repos** : le Conductor, la preuve et la mutation ne lisent que le premier repo du profil.
- 🆕 **OPP-48 · Déclencheurs d'escalade subtils** : désaccord persistant, build instable.
- 🆕 **OPP-49 · La Rehearsal en parallèle** (`parallel-conductor`, principes au PRD §7). **Déjà là** : une session par élément (0.28.0), lancées côte à côte par Maestro jusqu'à `max_running` (0.35.0) ; isolé par Rehearsal : ID, worktree, état `<ID>.json`, dossier `.ballet/run/<ID>/`, dispatches. Reste : un verrou sur le journal (ou la base, OPP-79) (le processus de mutation détaché et le Conductor y écrivent) ; les ports des preuves e2e simultanées ; un plafond de tâches lourdes (preuves, mutations) sur la machine ; les caches partagés (mise, `target/`) sans écriture concurrente.
- 🆕 **OPP-50 · Migrer Flownest** (PRD §16).

## Ménage

- 🆕 **OPP-51 · Les Runs Orca qui s'accumulent** : le Run du spike de mutation (`run_a0b4b533646e`) a disparu, mais au 22/11 `orca orchestration run-list` en garde 10 : six anciennes boîtes de Maestro (seule `run` de `maestro.toml` sert), « ballet probe » (spike 0002) et les Runs des Choreographers de FEAT-007 et FEAT-008. Orca n'a pas de commande pour fermer un seul Run, et `reset` efface tous les Runs, la boîte vivante comprise. À trouver : fermer un Run, ou un `mailbox` qui réutilise l'ancien Run au lieu d'en créer un.
