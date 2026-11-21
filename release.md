# Ballet — releases

Le journal des versions du plugin, la plus récente en haut. Chaque version a son tag git (`vX.Y.Z`), une ligne par fonctionnalité ou changement, et la liste des opportunités qu'elle traite (`opportunities.md`, cochées ✅ là-bas).

## 0.36.0 — 2026-11-21 · `v0.36.0`

Maestro, étape 4 sur 5 : le Monitor observe GitHub et les terminaux, et Maestro lance seul ce que le projet lui confie. OPP-01 ✅, OPP-02 (partiel).

- `ballet_monitor.py` (OPP-01), un script sans LLM : `once` (un tour) et `run [--interval <s>]` (en boucle, 180 s par défaut, jamais arrêté par une erreur passagère : `gh` ou Orca injoignable est noté et le tour suivant réessaie). Il écrit dans la boîte de Maestro, depuis son terminal Orca (`ORCA_TERMINAL_HANDLE`, par `ballet_maestro.post_status`, le chemin d'envoi d'`announce`), et ne lance rien ni ne parle au Director.
- **Un élément passé `ready`** : la file de chaque projet de `maestro.toml` est lue par `ballet_program.ready_items` (qui rend maintenant aussi le lien de l'issue) ; un nouvel élément prêt devient un `status` `<projet>#<N> · ready` (corps : numéro, type, priorité, titre, lien). Les éléments prêts de chaque projet sont gardés dans `~/.ballet/monitor.json` (écriture atomique sous verrou `monitor.lock`) : un élément encore prêt n'est pas signalé deux fois, un élément qui sort de `ready` puis y revient l'est de nouveau. Au premier tour d'un projet, les éléments déjà prêts sont groupés en un seul message (`<projet> · ready (<n> already)`). Un envoi qui échoue n'est pas noté : le tour suivant le refait ; une file illisible ne vide pas ce qui était connu.
- **Un Conductor disparu** : une ligne `running` du registre dont le terminal n'est plus dans Orca devient `<projet>#<élément> · gone` (priorité `high`) et passe à l'état `gone` (`ballet_conductors.mark_gone`), une seule fois. Les messages `ready` et `gone` du Monitor ne notent plus de Conductor dans le registre (`note_events` ne retient que `escalate` et `done`).
- `ballet_maestro.py monitor` crée le terminal du Monitor (`orca terminal create --title ballet-monitor --command "python3 <clone>/scripts/ballet_monitor.py run"`, `BALLET_HOME` transmis s'il est posé), une seule fois : rien ne se passe tant que le terminal noté (`[monitor] terminal`) vit. `/ballet:setup` l'appelle après `mailbox`.
- **La règle de lancement automatique de Maestro**, décidée par le script : `[projects.<alias>] auto_launch = ["Task", "Bug"]` dans `maestro.toml` (les types lancés seuls ; vide par défaut : Maestro demande toujours) ; `pause` et `resume` posent et retirent le drapeau `~/.ballet/auto_launch_paused` (en pause, rien ne part seul). `wait` et `recap` écrivent sous chaque élément `· ready` : `DECISION: launch` ou `DECISION: ask the Director (<raison>)`. `ballet_maestro.py ready` liste les éléments prêts sans Conductor, dans l'ordre de la file ; `status` les montre aussi. Un lancement refusé par un plafond laisse l'élément dans `ready`. Un élément dont le dernier Conductor a disparu (`gone`) n'est jamais relancé seul : `DECISION: ask the Director (its last Conductor is gone …)`, pour ne pas relancer en boucle un Conductor qui meurt au démarrage ; relancé par le Director, il retrouve la règle. `project add` sur un alias connu garde son `auto_launch`.
- Le skill `/ballet:maestro` : sur `DECISION: launch` il lance par `ballet_launch.py` puis le dit après coup ; sur `ask` il demande et lance sur le oui ; sur `gone` il le dit et propose de relancer, sur le oui seulement ; après un `done` ou un `gone` il regarde `ready` ; commandes `pause`, `resume`, `ready`. Il ne surveille toujours rien. `/ballet:setup` crée le Monitor, README, PRD §3 et spike à jour (`auto_launch` par projet, pas `[maestro]`).
- Vérifié en vrai sur Orca, `BALLET_HOME` temporaire : `once` sur antimurphy (une Feature prête, lue sans rien modifier) groupé au premier tour, rien au second ; `monitor` deux fois, un seul terminal, qui lance bien `ballet_monitor.py run` avec le `BALLET_HOME` ; un Conductor factice (`BALLET_CONDUCTOR_COMMAND="echo fake-conductor"`) lancé puis son terminal fermé : `· gone` reçu une fois, ligne marquée `gone` ; `DECISION`, `ready`, `pause` et `resume` lus dans la boîte. Puis la chaîne entière dans une vraie session `/ballet:maestro` : le Monitor, dans son propre terminal, signale une Feature prête d'antimurphy ; Maestro se réveille, lit `DECISION: launch` et lance seul le Conductor (factice) dans le dossier du projet ; son terminal fermé, le Monitor envoie `gone` et Maestro propose de relancer sans le faire. Terminaux de test fermés.
- Pas livré : le Conductor figé (OPP-75, 🆕), `stop` et `restart --when-idle` (étape 5), le headless et le gardien (OPP-74), le déclencheur à heure fixe du Workshop (OPP-06).

**Opportunités traitées** : OPP-01 ✅ ; OPP-02 (étape 4 sur 5, reste 🆕) ; OPP-75 créée.

## 0.35.0 — 2026-11-21 · `v0.35.0`

Maestro, étape 3 sur 5 : Maestro lance les Conductors, par un script à part, et le registre devient complet. OPP-02 (partiel).

- `ballet_launch.py` (appelé par Maestro seul) : `rehearsal <projet> <élément>` (`#12`, `12` ou `FEAT-002`) et `workshop <projet> [<élément>]` (toujours en autopilot ; sans élément, la première ligne de *Next up* sans Workshop, via `ballet_workshop.next_item`). Il ouvre un terminal Orca dans le dossier du projet (`orca terminal create --worktree path:<projet> --title '<projet>#<élément>' --command …`) qui lance `claude --remote-control '<projet>#<élément>' '/ballet:rehearsal #N' --allowedTools 'Bash(python3:*)' 'Edit(.ballet/run/**)'` : le prompt avant les options (`--allowedTools` avale ce qui la suit), `python3` seul autorisé en Bash, puisqu'un Conductor ne lance que les scripts de Ballet (`gh`, `git`, `orca` sont leurs affaires), et l'écriture sous `.ballet/run/` seulement, pour le message Ballet du Director (vérifié en mode de permission par défaut : aucune demande). `BALLET_CONDUCTOR_COMMAND` remplace `claude` (arguments inchangés) pour essayer sans tokens. Il affiche une ligne : ce qui est parti, où, le terminal, l'URL Remote Control. Un dossier qu'Orca ne connaît pas est refusé en donnant la commande `orca repo add --path …`.
- Quatre garde-fous avant tout lancement, chacun avec son refus (aucun terminal n'est créé) : projet connu de `maestro.toml` ; pas de Conductor vivant sur l'élément (ligne `running` du registre dont le terminal vit, ou session ouverte du projet, lue par `ballet_maestro.sessions_of`) ; plafond de Conductors simultanés ; plafond de lancements du jour. Les plafonds sont la table `[limits]` de `maestro.toml` : `max_running` (3) et `max_per_day` (10). Un lancement à la fois (`launch.lock`) ; Orca injoignable, rien n'est lancé.
- L'URL Remote Control est lue dans le terminal (`orca terminal read --screen`, jusqu'à 8 secondes) ; absente, la ligne la laisse vide.
- `ballet_conductors.py` : le registre `conductors.json`, lecture et écriture à un seul endroit (sous verrou, atomique), pour `ballet_launch.py` et `ballet_maestro.py`. Une ligne par `<projet>#<élément>` : projet, élément, genre, terminal, URL, `started` et `starts` (le plafond du jour), `seen`, `event`, et `state` (`running`/`finished`). `wait` et `recap` y notent toujours le terminal et le dernier événement ; un `done` marque la ligne `finished`, un autre événement la rouvre ; un Conductor lancé à la main y entre à son premier message. Les lignes de 0.34.0 se relisent.
- `ballet_state.py` : le dossier `~/.ballet` (chemin, écriture atomique, verrou), sorti de `ballet_maestro.py` pour être partagé.
- `status` montre aussi les Conductors du registre avec l'état de leur terminal (`alive`, `gone`, ou `state unknown` quand Orca ne répond pas) ; un Conductor fini dont le terminal est fermé n'est plus montré. `tell` marche dès le lancement, le terminal étant noté avant tout message.
- Le skill `/ballet:maestro` : `launch <projet> <élément>` et `launch <projet> --workshop [<élément>]`, sur demande du Director seulement ; il lui dit ce qui est parti et l'URL Remote Control. « launch à venir » retiré. README et `/ballet:setup` à jour.
- Vérifié en vrai sur Orca (terminal dans le bon dossier, ligne du registre, doublon et plafond refusés, `tell` reçu, URL d'un vrai `claude --remote-control` lue). Traite OPP-02 en partie (étape 3 sur 5, l'opportunité reste 🆕).

## 0.34.0 — 2026-11-21 · `v0.34.0`

Maestro, étape 2 : la session `/ballet:maestro`, et la garantie qu'une seule session lit la boîte.

- Le bail de lecture, dans `maestro.toml` : `[lease]` devient `owner` (un jeton aléatoire), `pid` (l'attente en cours, 0 sinon) et `renewed` (date ISO). Un bail est vivant si son `pid` tourne (un `ps` vérifie que c'est bien une attente de Maestro, pas un pid repris), ou s'il a été renouvelé il y a moins de 10 minutes. Un ancien `[lease]` (`pid`, `since`) se relit sans erreur.
- `ballet_maestro.py claim` : refuse quand une autre session tient un bail vivant (le message propose `--take-over`), sinon écrit et affiche un jeton. `claim --take-over` arrête l'attente de l'ancien propriétaire (`SIGTERM`, qui arrête aussi son `orca check`) puis prend le bail. Tout sous le verrou existant.
- `wait --owner <jeton>` : refuse (`this session is not Maestro anymore: …`) un jeton qui ne tient pas le bail, ou une seconde attente du même jeton ; note son pid, lit `orca orchestration check --wait` (en consommant, jamais `--peek` ; une attente qui expire repart), remet `pid = 0` et renouvelle `renewed` même en cas de panne, sans toucher à un bail repris entre-temps. Il affiche sujet, priorité, expéditeur et corps, et note dans `~/.ballet/conductors.json` (écriture atomique) le terminal expéditeur de chaque `status` `<projet>#<élément> · <événement>`, avec la date et le dernier événement.
- `recap --owner <jeton>` : au démarrage, le non-lu, consommé (aucun `wait` ne le redonne et ses Conductors sont notés), et les 10 derniers messages de l'historique (`orchestration inbox --full`, filtré sur la Run de la boîte), la Run `previous_run` d'une boîte recréée comprise, qu'on oublie ensuite. Seul le jeton qui tient le bail lit.
- `status` : une ligne par session ouverte de chaque projet (élément, Rehearsal courante, état, terminal connu), lue avec les fonctions de `ballet_rehearsal.py` (`session-*.json`) et `ballet_workshop.py` (`workshop-*.json`) ; rien n'est créé dans un projet.
- `tell <projet>#<élément> <texte>` : `orca terminal send --text "Director answers: <texte>" --enter` vers le terminal du registre ; un élément inconnu, une cible mal écrite ou un terminal disparu sont refusés. Le Conductor écrit lui-même le message Ballet et lance `receive`.
- Le skill `/ballet:maestro` : `claim` au démarrage (le bail pris est signalé, `--take-over` seulement sur le oui du Director), `recap` et `status`, un résumé « While you were away: … » (ou « Nothing new »), puis `wait` en arrière-plan, une seule à la fois, rapportée à chaque réveil (motif, liens, ce qu'il faut décider) ; `status` et `tell` à la demande du Director, avec l'avertissement que la réponse part au terminal du Conductor ; `launch` et `stop` annoncés comme à venir. Il n'interroge jamais GitHub.
- `/ballet:setup` : sa dernière étape dit d'ouvrir `/ballet:maestro`. README mis à jour.

**Opportunités traitées** : OPP-02 (étape 2 sur 5, reste 🆕).

## 0.33.0 — 2026-11-21 · `v0.33.0`

Maestro, étape 1 : sa boîte Orca, où les Conductors écrivent leurs escalades et leurs fins, et un premier `/ballet:setup`.

- Le superviseur s'appelle Maestro (`/ballet:maestro`, `ballet_maestro.py`, `~/.ballet/maestro.toml`) ; Maestro et le Monitor entrent au vocabulaire (PRD §3, `AGENTS.md`), et le spike 0001, OPP-01, OPP-02 et OPP-74 suivent.
- `ballet_maestro.py mailbox` crée la boîte de Maestro, une seule fois : un terminal Orca vide (`maestro-mailbox`), puis une Run `run-create --from` lui. Le terminal noté vit encore : rien ne change. Il a disparu : une nouvelle boîte, l'ancienne Run gardée (`previous_run`) pour une dernière lecture. Orca injoignable : rien n'est créé. Un verrou empêche deux appels de créer chacun la sienne.
- `ballet_maestro.py project add <alias> <chemin>` et `project list` : les projets de Maestro.
- `~/.ballet/maestro.toml` (`BALLET_HOME` pour un autre dossier) : `[mailbox]`, `[projects.<alias>]` et la place du bail `[lease]` (pid, début), qui servira à l'étape 2. Écrit d'un coup (fichier temporaire puis renommage), par un sérialiseur TOML minimal.
- `ballet_rehearsal.py` et `ballet_workshop.py` annoncent à Maestro chaque transition qui finit en `NEXT: escalate` (question comprise) ou `NEXT: done` : `orchestration send --to run:<id> --type status --priority high`, sujet `<projet>#<élément> · <événement>` (l'alias du projet, sinon le nom du dossier), le pas entier en corps. Une lecture (`status`, un `resume` sans rien à reprendre) n'est pas annoncée. Sans `maestro.toml` ou sans boîte, rien n'est envoyé ; un échec d'envoi n'est qu'une ligne du pas (`Maestro not told: …`). Une panne avant que la session existe (profil invalide, élément déjà en session) est annoncée aussi, sous l'élément nommé sur la ligne de commande (`?` sinon) ; une panne de `status`, simple lecture, ne l'est pas.
- PRD : l'observateur qui lançait les sessions devient le Monitor qui signale et Maestro qui lance (§6, §7, §11, §15, §17).
- Le skill `/ballet:setup`, présentiel seulement : vérifie les outils (`git`, `python3`, `gh auth status`, `claude`, `orca`), lance `reset_plugin.py` du clone, enregistre les projets (`ballet_maestro.py project add`, `orca repo add`), propose `/ballet:init-project` aux projets sans profil, crée la boîte, et dit ce qui reste à venir (la session Maestro, le Monitor, le headless). README mis à jour.

**Opportunités traitées** : OPP-02 (étape 1 sur 5, reste 🆕) ; OPP-74 (premier setup, reste 🆕).

## 0.32.1 — 2026-11-20 · `v0.32.1`

Le Dancer lançait la preuve complète à chaque tâche (FEAT-006 sur antimurphy : une douzaine de preuves, e2e compris, puis une de plus par le script, l'essentiel des 45 minutes).

- Après chaque tâche, le Dancer ne lance que les tests liés : le test qu'il a écrit et ceux du même niveau autour de ce qu'il a changé (crate ou paquet, fichier de test, scénarios `@FEAT-NNN-Cn` du critère), plus les vérifications rapides de la preuve sur les fichiers touchés (format, lint, types). Il commite sur ce vert.
- La preuve du repo tourne une seule fois, verte, avant le rapport (et avant chaque nouveau rapport après le Critic, s'il a commité). Plus de preuve au démarrage : la branche part de `main`, déjà prouvé ; une panne dans du code que ses tâches n'ont pas touché se vérifie sur le commit de départ et se signale.
- Skill Dancer mis à jour (description, étape 4, section « Prove, check, then report », tours du Critic).

**Opportunités traitées** : OPP-72.

## 0.32.0 — 2026-11-20 · `v0.32.0`

Le Workshop autopilot, fin d'OPP-06 hors Scène : l'avis du Choreographer, la marque des décisions prises seul, et le choix dans le backlog.

- Le Dramaturg consulte le Choreographer avant d'écrire, quand la feature touche un choix technique, par le Conductor comme en Rehearsal : chaque question (`type: question`, `to: choreographer`) et chaque réponse réveille le Conductor, qui lance `receive`. Le script lance le Choreographer en worker dans le même worktree à la première question, lui envoie les suivantes dans sa session, le juge comme le Critic à chaque réponse (rien n'a bougé : sinon `policy: the choreographer broke the rules`) et rend la réponse au Dramaturg. Les tours n'ont qu'une borne, `[escalation] max_exchange_rounds` (le profil du projet l'emporte sur celui du plugin), comptée par le script et non lue dans l'en-tête. Le Choreographer n'écrit ni plan ni ADR. Une reprise (`resume`) relance un Choreographer qui n'avait pas pu démarrer.
- La trace : chaque question et réponse est au journal au fil de l'eau (`message`, `handoff`, `policy`, clé `workshop` : l'élément, jamais renommé), puis commentée sur l'issue, dans l'ordre, dès que le script la crée (la Rehearsal les publie au fil de l'eau ; ici, l'issue naît à la fin). Un commentaire qui échoue se reprend sans doublon. À la publication, l'événement `published` (`{"item": "BUG-004", "issue": "21", "type", "status", "picked", "decided_alone", "exchanges"}`) lie l'élément à son issue, comme `handover` lie une planification à sa slice : la Scène suit `BUG-004` → `#21` → sa Rehearsal sans rien relire sur GitHub.
- Ce que le Dramaturg a décidé seul (`## Decided alone`) est recopié dans l'issue, avant son plan, et l'issue porte le libellé `ballet:decided-alone` ; sans décision, ni section ni libellé. Nouvelle opération `decided-alone <issue>` de `ballet_github.py` ; un libellé qui échoue se reprend sans republier l'issue.
- `[workshop] queue_approval_skipped` s'ouvre à `Feature` dans la doc (le profil l'acceptait déjà) : README, PRD et `config.toml` disent le risque (une feature fait deviner du métier) et ce qui permet de le relire, la marque.
- `ballet_workshop.py begin` sans élément : le Workshop choisit la première ligne de *Next up* (OPP, FEAT, BUG ou TASK, jamais `CAP-`) qui n'a encore aucune session, et la prend pour nom de session. Ce qu'il choisit seul sort toujours `proposed`, quoi que dise `queue_approval_skipped`. `/ballet:workshop --autopilot` sans élément le lance ; le Dramaturg sort la ligne de *Next up* une fois cadrée.
- Skills Dramaturg (consultation, `Decided alone`, ligne rangée), Choreographer (consulté en autopilot), Conductor (section Workshop) et Workshop mis à jour ; PRD (§6) et README.

- Une demande hors backlog : `ballet_workshop.py begin --request "<demande>"` (`/ballet:workshop --autopilot "<demande>"`) nomme la session d'un slug (ses six premiers mots, sans accents, suffixé `-2` s'il a déjà servi) : `workshop-<slug>.json`, branche `workshop/<slug>` (acceptée par `push` et `merge-specs`). Le Dramaturg la capture d'abord, puis cadre la ligne où elle tombe, qu'il nomme dans son rapport (`- Item:`, exigé, renvoyé une fois sinon) ; `published` lie le slug à cette ligne et à l'issue. Le profil s'applique comme pour un élément nommé.

**Opportunités traitées** : OPP-70 (troisième partie d'OPP-06) ; la capture d'une demande hors backlog laissée par OPP-68.

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
