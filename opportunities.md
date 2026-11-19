# Ballet — opportunités

Ce qui reste à faire, à vérifier ou à trancher dans Ballet. La méthode est dans `PRD.md`, ce qui est livré dans `release.md`.

- 🆕 à traiter · ✅ traité (avec la version qui l'a livré, reportée dans `release.md`)
- Un sujet garde son numéro pour toujours ; un sujet traité reste ici, coché. Pas de doublon : un nouveau besoin proche d'un sujet existant l'enrichit.
- Dans chaque section, du plus pressé au plus lointain.

## La vision

- **Deux sessions de Conductor par projet, toujours actives**, sur la machine du Director ou un VPS : une pour le Workshop, une pour la Rehearsal. Quand la file est vide et que le contexte passe un seuil, la session se vide (`/clear`) sans perdre sa casquette de Conductor.
- **Un Supervisor** (nom à trouver) est le point d'entrée unique du Director. Il passe ses instructions aux Conductors : par message entre sessions, ou, plus simple pour les features à traiter, en les inscrivant dans la file du projet, que le Conductor de Rehearsal surveille.
- **Chaque boucle tourne en `assisted` par défaut**, ou en `autopilot` quand on la lance ainsi.
- **Le Workshop** : en assisted, le Director et le Dramaturg, et le Choreographer quand on veut aller jusqu'au plan ; en autopilot, le Dramaturg et le Choreographer seuls. Sortie : une feature prête, ou l'issue et ses slices créées avec leur plan.
- **La Rehearsal** part d'une feature prête (le Choreographer planifie d'abord) ou d'un plan fait au Workshop (le Dancer enchaîne), jusqu'à la Premiere. En assisted, elle escalade vers le Director ; en autopilot, c'est le mode nuit.
- **Le Choreographer est le pivot** : il joue dans les deux boucles.
- **En autopilot, chacun décide dans son périmètre** : le Dramaturg tranche le métier ; le Choreographer l'architecture, et demande le métier au Dramaturg ; le Dancer suit l'architecture, et demande au Choreographer. Le Director ne reçoit que ce qui sort de tous les périmètres, et relit après coup les décisions, tracées en ADR (architecture), specs ou rapport (métier).

## Les deux boucles et le Supervisor

- 🆕 **OPP-01 · Deux sessions de Conductor permanentes par projet** (Workshop, Rehearsal) : chacune attend du travail au lieu de s'arrêter en fin de file ; file vide et contexte au-delà d'un seuil, elle se vide (`/clear`) et recharge son skill de Conductor.
- 🆕 **OPP-02 · Le Supervisor** (nom à trouver, au vocabulaire du PRD §3) : le point d'entrée du Director, pour tous ses projets. Il inscrit les features à traiter dans la file du projet, et parle aux Conductors par message entre sessions pour le reste.
- 🆕 **OPP-03 · La file du projet, surveillée par le Conductor de Rehearsal** : une file qui vit au-delà d'un run (aujourd'hui `.ballet/run/queue.json`, créée par `run` et finie à son dernier élément), où le Supervisor et le Workshop écrivent ; le Conductor de Rehearsal la sonde et ouvre l'élément qui arrive.
- 🆕 **OPP-04 · Deux modes par boucle, `assisted` par défaut et `autopilot` au lancement** : en autopilot, chacun décide dans son périmètre (voir la vision) et trace sa décision ; le Director ne reçoit que ce qui sort de tous les périmètres.
- 🆕 **OPP-05 · Workshop assisted** : le Director et le Dramaturg (le `/ballet:dramaturg` d'aujourd'hui), et le Choreographer quand on veut aller jusqu'au plan. Sortie : une feature prête, ou l'issue et ses slices créées avec leur plan, versées à la file du projet.
- 🆕 **OPP-06 · Workshop autopilot** : le Dramaturg et le Choreographer, sans le Director. Il cadre une demande, un bug ou un retour, ou choisit lui-même dans le backlog (en propositions d'abord : des features que le Director valide). Sortie : des features prêtes et des issues découpées en slices avec leur plan, versées à la file du projet.
- 🆕 **OPP-07 · Rehearsal : deux points d'entrée, deux modes** : une feature prête sans plan (le Choreographer commence) ou un plan fait au Workshop (le Dancer enchaîne), les deux existent déjà ; assisted, elle escalade vers le Director (approbation du plan comprise, aujourd'hui `--plan review`) ; autopilot, le mode nuit, les décisions prises par périmètre et partagées (ADR, rapport).
- 🆕 **OPP-08 · Retirer `hybrid-track`** : on lance une boucle par son nom et son mode (par exemple `/ballet:workshop`, `/ballet:rehearsal --autopilot`, noms à trancher). Le PRD suit : la Piece, les axes et le répertoire (§3, §6, §7.1) laissent la place aux deux boucles, à leurs deux modes et au Supervisor.

## Premier vrai run de la mutation (antimurphy)

- 🆕 **OPP-09 · Le projet porte l'outil** : la TASK du Choreographer (ADR 0007 mise, `mise.toml` avec cargo-mutants 27.1.0, `.cargo/mutants.toml`, `mutants.out/` dans le `.gitignore`), la CI passée à mise à la main, puis l'entrée `[[repos.antimurphy.mutation]]` du profil, à la main par le Director.
- 🆕 **OPP-10 · Sorties dans le `.gitignore`** : un `mutants.out/` non ignoré salit le worktree, et le passage suivant du Dancer est refusé pour un worktree sale. À vérifier dès le premier run.
- 🆕 **OPP-11 · À observer sur ce run** : le réveil de fin de mutation dans une vraie session de Conductor (vérifié dans le spike, pas encore dans une Rehearsal), la durée réelle par slice, les survivants remis au Dancer et ce qu'il en fait (test unitaire ou exclusion), le jugement du Critic sur les exclusions.

## Mutation : trous connus

- 🆕 **OPP-12 · Reprendre après une escalade avant la PR** : mutation rouge au-delà de `max_round_trips`, trop longue, en panne, ou worktree qui a bougé ; même trou pour la preuve. `resume` répond « no pull request yet ». Donner au Director un moyen de trancher : relancer, passer, ou renvoyer au Dancer.
- 🆕 **OPP-13 · Un réveil perdu** : si le message Orca ne part pas (`mutation-wake` avec `sent: false`), le Conductor attend sans le savoir. `receive --mutation` rattrape, encore faut-il y penser. Pistes : `status` signale une mutation finie mais non reçue, ou la Scène le montre.
- 🆕 **OPP-14 · Le coût par tour** : la mutation tourne à chaque rapport du Dancer, tour des notes compris, sur tout le diff. Une fois les durées mesurées, ne muter que ce qui a changé depuis la dernière mutation verte.
- 🆕 **OPP-15 · La politique signale les changements du `config` de l'outil** (les exclusions), pour que le Critic ne les rate pas.
- 🆕 **OPP-16 · Les recettes par stack dans `init-project`** : l'entrée `mutation` toute prête pour Rust (cargo-mutants `--in-diff {diff}`), TS (StrykerJS `--mutate {ranges}`), JVM (PIT).
- 🆕 **OPP-17 · Les lecteurs `stryker` et `pit`** dans `ballet_mutation.py`, chacun vérifié sur un vrai rapport (fixture dans `tests/fixtures/`). Le front d'antimurphy attend les contournements du pilote : TypeScript 7, pnpm, le bac à sable de Stryker.
- 🆕 **OPP-18 · Le Critic ne relance plus la preuve ni la mutation** lui-même, une fois les nœuds du script éprouvés.

## Rehearsal et file

- 🆕 **OPP-19 · Modifier un plan en review** (`--plan review`) : aujourd'hui le Director l'édite à la main sur l'issue, ou abandonne la file en supprimant `.ballet/run/queue.json`. Renvoyer le plan au Choreographer avec ses remarques, dans sa session.
- 🆕 **OPP-20 · Une feature déjà planifiée relancée** (`run FEAT-002` une seconde fois) : le Choreographer recréerait son issue. Chercher l'issue existante avant d'ouvrir la planification, et jouer ses slices ouvertes.
- 🆕 **OPP-21 · Une parente dans la file** (`run #13`) : sans tâches propres, elle repart en planification. Une parente qui a des slices ouvertes se déroule en ses slices, dans l'ordre.
- 🆕 **OPP-22 · Compter les tours par point, pas par issue** : au premier run, 3 questions sur 3 sujets différents auraient escaladé à tort. Trancher : un sujet par point (`#2/wasm-outdir`) ou `round` remis à 1 sur une nouvelle question.
- 🆕 **OPP-23 · Les notes déclinées adressées au Choreographer** (amender une décision, fixer un contrat pour la slice suivante) se perdent dans la PR au merge. Les lui porter, ou les reporter sur la parente ou la slice suivante.
- 🆕 **OPP-24 · Une troisième catégorie du Critic**, à côté des points bloquants et des notes : opportunité, vigilance, bug hors du diff, versée au backlog du Dramaturg. Circuit à définir.
- 🆕 **OPP-25 · Taille des slices, à mesurer** : la règle 0.23.0 (le moins de slices possible, verticales, sous les deux tiers du seuil, fusion des voisines) n'a pas encore été vue sur une feature ; trancher ensuite entre découpage et seuil, sur les `diff-size` du journal.
- 🆕 **OPP-26 · Le Choreographer vérifie l'outillage** dont dépend son plan (version, comportement) par un spike, plutôt que de reprendre `AGENTS.md` (cas : isolation D1 de `@cloudflare/vitest-plugin` 1.8.2).
- 🆕 **OPP-27 · Vérifier `label` sur un vrai repo** : création des libellés, `--remove-label` d'un libellé absent de la PR.
- 🆕 **OPP-28 · Les sous-issues natives de GitHub** plutôt que la ligne `Part of #N` et la recherche (avancement visible sur la parente).

## Politique et GitHub

- 🆕 **OPP-29 · L'état GitHub de l'issue et de la PR inchangé** pendant le passage d'un rôle (sauf le Choreographer sur son issue et ses slices).
- 🆕 **OPP-30 · Un commit appartient au rôle du passage où il est apparu** : le Conductor relève l'état du repo à chaque relais ; au `ask` du Dancer, l'arbre non commité est vérifié ; au retour du Choreographer, l'arbre non commité est inchangé ; un registre sha → rôle hors du worktree, vérifié avant la Premiere. Limite : tient tant que le Dancer ne peut pas écrire dans le dossier du Conductor (voir la signature par rôle, PRD §17).
- 🆕 **OPP-31 · Le Choreographer a son propre worktree pour ses spikes** quand il répond au Dancer : aujourd'hui son `checkout` passe par-dessus le travail en cours du Dancer.
- 🆕 **OPP-32 · Le Dramaturg en Workshop** (sur `main`, hors Conductor) n'est pas vérifié par la politique.
- 🆕 **OPP-33 · Un test existant dont le corps change** (une attente affaiblie) : aujourd'hui, seul le Critic le voit.
- 🆕 **OPP-34 · Chaque violation du PRD §5.3 couverte par un test**, sur des repos jouets.
- 🆕 **OPP-35 · Le script GitHub, opérations manquantes** : cocher une tâche du plan, journaliser chaque appel (opération, entrées, résultat).
- 🆕 **OPP-36 · Figer le format du journal** (`.ballet/run/journal.jsonl` : `at`, `rehearsal`, `event`, `detail`).

## Rôles et règles

- 🆕 **OPP-37 · Les règles communes chargées par chaque rôle** : tdd et clean code partout, et une règle trunk-based qui n'existe pas encore.
- 🆕 **OPP-38 · Ajuster les rôles et les seuils sur les runs réels** : lire le journal (refus du Critic, allers-retours, builds rouges, merges à corriger après coup), jusqu'à un avis chiffré sur la qualité du Critic.
- 🆕 **OPP-39 · Le Dramaturg : parcours, flux et expérience** (le `/storyboard` de flownest).
- 🆕 **OPP-40 · Partager les skills user de Claude avec Vibe** (lien `~/.vibe/skills` → `~/.claude/skills`), une fois le ménage des skills user fait.

## CLI et modèles

- 🆕 **OPP-41 · Grok** : vérifier `/ballet:dramaturg`, le priver du jeton GitHub par l'environnement du lancement, le limiter au dossier de travail (`--sandbox workspace` n'a rien bloqué sous `/tmp`). Bloqué par la limite d'usage gratuit.
- 🆕 **OPP-42 · Dancer Claude puis Dancer Mistral** sur les mêmes issues, et comparaison (PRD §9) ; Mistral Vibe lancé par le Conductor.

## La Scène

- 🆕 **OPP-43 · Finir la Scène v2** (`stage/v2.html`, servie sur `/v2`) et retirer la v1 une fois l'usage éprouvé.
- 🆕 **OPP-44 · La mutation sur la Scène** : `mutation-start`, `mutation-end`, `mutation-skipped` et `mutation-wake` au fil, avec le score et les survivants, et « mutation running » dans la phase.
- 🆕 **OPP-45 · La Scène, ensuite** : valider le nom au vocabulaire (PRD §3), les temps par phase, la comparaison des modèles, un registre de projets.

## Profil

- 🆕 **OPP-46 · Ranger le profil** : une table par étape (`[proof] timeout_seconds` au lieu de `[escalation] proof_timeout_seconds`, comme `[mutation]`) ; `plan_approval`, choix de workflow, hors de `[escalation]`, qui ne garde que les seuils qui font remonter au Director. Casse les profils existants : migration par `init-project`.

## Plus loin

- 🆕 **OPP-47 · Projet multi-repos** : le Conductor, la preuve et la mutation ne lisent que le premier repo du profil.
- 🆕 **OPP-48 · Déclencheurs d'escalade subtils** : désaccord persistant, build instable.
- 🆕 **OPP-49 · `parallel-conductor`** (`hybrid-parallel`, principes au PRD §7). Déjà isolé par Rehearsal : ID, worktree, état `<ID>.json`, dossier `.ballet/run/<ID>/`, dispatches. À reprendre : la file à une seule Rehearsal `current` et l'ID facultatif des commandes ; un verrou sur le journal (le processus de mutation détaché et le Conductor y écrivent) ; les ports des preuves e2e simultanées ; un plafond de tâches lourdes (preuves, mutations) sur la machine ; les caches partagés (mise, `target/`) sans écriture concurrente.
- 🆕 **OPP-50 · Migrer Flownest** (PRD §16).

## Ménage

- 🆕 **OPP-51 · Le Run Orca du spike de mutation** (`run_a0b4b533646e`, « Spike: mutation wake ») reste dans `orca orchestration run-list`, vide ; Orca n'a pas de commande pour fermer un seul Run, et `reset` efface tous les Runs.
