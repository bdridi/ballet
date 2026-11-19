# Ballet — opportunités

Ce qui reste à faire, à vérifier ou à trancher dans Ballet. La méthode est dans `PRD.md`, ce qui est livré dans `release.md`.

- 🆕 à traiter · ✅ traité (avec la version qui l'a livré, reportée dans `release.md`)
- Un sujet garde son numéro pour toujours ; un sujet traité reste ici, coché. Pas de doublon : un nouveau besoin proche d'un sujet existant l'enrichit.
- Dans chaque section, du plus pressé au plus lointain.

## La vision

- **La file, c'est GitHub.** Une issue a un type (`task`, `bug`, `feature`, `slice`) et un statut ; une `task`, un `bug` ou une `feature` au statut prêt attend sa Rehearsal. Les slices naissent de la planification d'une feature et se jouent à sa suite.
- **Un observateur déterministe** (un script, pas un agent) surveille la file et lance une session de Conductor neuve pour l'élément prêt suivant, une à la fois. L'état vit dans les scripts et sur GitHub : rien à garder en mémoire d'une session à l'autre.
- **Chaque boucle tourne en `assisted` par défaut**, ou en `autopilot` quand on la lance ainsi.
- **Le Workshop sort une feature prête, jamais un plan.** Le Choreographer y donne son avis technique tôt, parce qu'il peut changer le choix produit. En assisted, le Director, le Dramaturg et le Choreographer ; en autopilot, le Dramaturg et le Choreographer seuls, et la feature sort proposée, prête une fois que le Director l'accepte ; le full autopilot (prête d'emblée) reste une option.
- **La Rehearsal planifie sur le vrai `main`** : le Choreographer commence par le plan, juste avant le Dancer, pour qu'il ne se périme pas. En assisted, elle escalade vers le Director ; en autopilot, c'est le mode nuit.
- **En autopilot, chacun décide dans son périmètre** : le Dramaturg tranche le métier ; le Choreographer l'architecture, et demande le métier au Dramaturg ; le Dancer suit l'architecture, et demande au Choreographer. Ce qui est décidé sans le Director est marqué et réuni dans un rapport du matin ; il ne reçoit en direct que ce qui sort de tous les périmètres.
- **Un budget** borne ce que l'autopilot dépense.
- **Plus tard, un Supervisor** (nom à trouver), le point d'entrée du Director pour plusieurs projets.

## Les deux boucles et la file

- 🆕 **OPP-01 · L'observateur** : un script déterministe (ou une automation Orca) qui surveille la file sur GitHub et lance une session de Conductor neuve par élément prêt, une à la fois ; à la Premiere, il passe au suivant. Remplace le `run` lancé à la main (la file locale disparaît avec OPP-55).
- 🆕 **OPP-02 · Le Supervisor** (nom à trouver), pour plusieurs projets : arbitrer les priorités et le budget entre eux, résumer le matin. À affiner une fois deux projets en route.
- ✅ **OPP-03 · La Scène montre le programme depuis GitHub** (0.27.0) : la liste « à faire » de la Scène (v1, et v2 qui lit les mêmes données) vient des issues GitHub du projet : les types `Feature`, `Bug` et `Task` dont le champ Ballet status est `ready`, dans l'ordre du champ Priority puis de l'ancienneté (les `Slice` suivent leur feature). Chaque session de Conductor ouverte (aujourd'hui `queue.json`, une seule ; plusieurs avec OPP-55) montre son élément confié, ses slices qui restent et sa Rehearsal courante, avant le programme, qui n'a plus les éléments qu'une session a pris ; l'historique vient du journal `.ballet/run/journal.jsonl` et des états des Rehearsals. Lecture seule, avec un cache de quelques dizaines de secondes ; si `gh` échoue, la page dit « programme indisponible » au lieu d'une liste vide. **Fini quand** sa liste « à faire » est celle de GitHub, et que les sessions ouvertes sont montrées à part. Déjà là (0.26.0) : `init-project` crée le type `Slice` et les champs `Ballet status`, `Rehearsal mode` et `Priority` chez le propriétaire (`ballet_planning.py`). Valeurs : Ballet status = `proposed`, `ready`, `in-rehearsal`, `plan-review`, `escalated`, `done` ; Rehearsal mode = `assisted`, `assisted + plan approval`, `autopilot` (vide, `assisted`) ; Restent des libellés ce qui vit sur la PR (verdicts, taille) et la marque `ballet:decided-alone`.
- ✅ **OPP-55 · Une session de Conductor par élément confié** (0.28.0) : `/ballet:rehearsal #12` (ou `FEAT-002` tant qu'une feature n'a pas d'issue) confie un seul élément, une `Feature`, un `Bug` ou une `Task`, à un Conductor, qui le joue jusqu'à sa dernière Premiere ; le script l'ouvre par `begin <élément>` (plus de `run`, ni de liste, ni de `--plan`). L'état local est une session par élément (`.ballet/run/session-12.json`, `session-FEAT-002.json`) : l'élément, son issue, ses slices dans l'ordre du plan, la Rehearsal en cours, ce qui est joué et le mode. Deux sessions tournent côte à côte sur deux éléments ; un élément déjà en session est refusé, qu'on le nomme par sa feature ou par son issue ; combien de sessions à la fois, c'est l'affaire de l'observateur (OPP-01). Le mode se lit sur le champ `Rehearsal mode` (vide : `assisted` ; `assisted + plan approval` arrête sur le plan, comme `--plan review`). Le script écrit `Ballet status` quand il change : `in-rehearsal`, `plan-review`, `escalated`, `done`. La Scène lit toutes les sessions ouvertes. L'approbation du plan elle-même ne change pas : OPP-57.
- ✅ **OPP-56 · Le Workshop publie la feature prête en issue `Feature`** (0.27.0, par le Dramaturg ; le Workshop autopilot reste à faire, OPP-06) : sans plan, par le script GitHub, au statut `ready` (ou `proposed` en autopilot) ; le Choreographer n'écrit plus que son plan et ses slices sur cette issue. Lié à OPP-05 et OPP-06 (les deux Workshops) et à OPP-28 (sous-issues natives).
- 🆕 **OPP-04 · Deux modes par boucle, `assisted` par défaut et `autopilot` au lancement** : en autopilot, chacun décide dans son périmètre et trace sa décision ; ce qui est décidé sans le Director porte une marque (par exemple `ballet:decided-alone`) et entre au rapport du matin.
- 🆕 **OPP-05 · Workshop assisted** : le Director, le Dramaturg (le `/ballet:dramaturg` d'aujourd'hui) et le Choreographer pour l'avis technique, tôt. Sortie : une feature prête, versée à la file.
- 🆕 **OPP-06 · Workshop autopilot** : le Dramaturg et le Choreographer, sans le Director. Il cadre une demande, un bug ou un retour, ou choisit lui-même dans le backlog. Sortie : des features proposées, que le Director accepte avant qu'elles entrent dans la file ; en option, le full autopilot les rend prêtes d'emblée.
- 🆕 **OPP-07 · Rehearsal assisted ou autopilot** : le Choreographer planifie au début, sur le vrai `main` (une issue qui a déjà son plan va droit au Dancer) ; assisted, le Director reçoit les escalades et le Choreographer enchaîne sur son plan, sauf avec `--require-plan-approval`, où il attend que le Director le valide ; autopilot, le mode nuit, le Director hors de la boucle, les décisions prises par périmètre.
- 🆕 **OPP-08 · Retirer `hybrid-track`** des skills, du README et des scripts (en partie, 0.28.0 : `/ballet:rehearsal` remplace `hybrid-track`, `--plan` et `plan_approval` ont disparu, le mode est le champ `Rehearsal mode` et le plan enchaîne par défaut ; restent `/ballet:workshop` et ce que l'autopilot change) : une commande par boucle avec son mode (`/ballet:workshop`, `/ballet:rehearsal [--autopilot]`, noms à trancher), `--plan review|auto` remplacé par le mode et `--require-plan-approval`. Le défaut s'inverse : aujourd'hui le plan attend le Director (`[escalation] plan_approval = true`), demain il enchaîne. Le PRD décrit déjà les deux boucles et leurs modes.
- 🆕 **OPP-52 · Le rapport du matin** : ce que la nuit a mergé, escaladé, et décidé sans le Director (ADR, specs, rapports), de quoi relire en quelques minutes.
- 🆕 **OPP-53 · Le budget de l'autopilot** : un plafond (par nuit, par projet ; en tokens, en temps ou en Rehearsals, à affiner) ; atteint, l'observateur n'ouvre plus rien et le dit.
- 🆕 **OPP-54 · Une escalade la nuit** : aujourd'hui, elle arrête toute la file et la nuit est perdue. Passer à l'élément suivant qui n'en dépend pas suppose de connaître les dépendances entre éléments (par exemple les dépendances natives de GitHub, « blocked by »).

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

- 🆕 **OPP-19 · Modifier un plan en review** (mode `assisted + plan approval`) : aujourd'hui le Director l'édite à la main sur l'issue, ou abandonne la session en supprimant son `.ballet/run/session-<élément>.json`. Renvoyer le plan au Choreographer avec ses remarques, dans sa session.
- 🆕 **OPP-20 · Une feature déjà planifiée relancée** (`/ballet:rehearsal FEAT-002` une seconde fois) : le Choreographer recréerait son issue. Chercher l'issue existante avant d'ouvrir la planification, et jouer ses slices ouvertes.
- 🆕 **OPP-21 · Une parente dans la file** (`/ballet:rehearsal #13`) : sans tâches propres, elle repart en planification. Une parente qui a des slices ouvertes se déroule en ses slices, dans l'ordre.
- 🆕 **OPP-22 · Compter les tours par point, pas par issue** : au premier run, 3 questions sur 3 sujets différents auraient escaladé à tort. Trancher : un sujet par point (`#2/wasm-outdir`) ou `round` remis à 1 sur une nouvelle question.
- 🆕 **OPP-23 · Les notes déclinées adressées au Choreographer** (amender une décision, fixer un contrat pour la slice suivante) se perdent dans la PR au merge. Les lui porter, ou les reporter sur la parente ou la slice suivante.
- 🆕 **OPP-24 · Une troisième catégorie du Critic**, à côté des points bloquants et des notes : opportunité, vigilance, bug hors du diff, versée au backlog du Dramaturg. Circuit à définir.
- 🆕 **OPP-57 · Comment le Director approuve un plan** : en mode `assisted + plan approval`, il pose aujourd'hui le libellé `ballet:plan-approved` sur l'issue planifiée puis fait reprendre (`resume`), pendant que le script écrit `Ballet status = plan-review`. Trancher : garder le libellé, passer par le champ (le Director repasse le statut à `in-rehearsal`), ou accepter les deux ; et ce que devient `ballet:plan-approved`. Lié à OPP-07, OPP-08 et OPP-19.
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
- 🆕 **OPP-49 · La Rehearsal en parallèle** (`parallel-conductor`, principes au PRD §7). Déjà isolé par Rehearsal : ID, worktree, état `<ID>.json`, dossier `.ballet/run/<ID>/`, dispatches. À reprendre : la file à une seule Rehearsal `current` et l'ID facultatif des commandes ; un verrou sur le journal (le processus de mutation détaché et le Conductor y écrivent) ; les ports des preuves e2e simultanées ; un plafond de tâches lourdes (preuves, mutations) sur la machine ; les caches partagés (mise, `target/`) sans écriture concurrente.
- 🆕 **OPP-50 · Migrer Flownest** (PRD §16).

## Ménage

- 🆕 **OPP-51 · Le Run Orca du spike de mutation** (`run_a0b4b533646e`, « Spike: mutation wake ») reste dans `orca orchestration run-list`, vide ; Orca n'a pas de commande pour fermer un seul Run, et `reset` efface tous les Runs.
