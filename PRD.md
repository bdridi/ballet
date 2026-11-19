# Ballet — PRD

> Méthode commune à tous mes projets pour faire travailler des agents de code (Claude, Grok, Mistral…) en chaîne, sur la plomberie d'Orca.
> Statut : cadrage, rien n'est construit. Version du 16 novembre 2026.

## 1. Pourquoi

- Je veux **une seule méthode** pour tous mes projets, Flownest compris, au lieu de skills recopiés et adaptés projet par projet.
- Je veux **déléguer une issue de bout en bout** à des agents (cadrage, plan, code, validation), avec plus ou moins d'autonomie selon le cas.
- Nightshift (usine sur GitHub Actions) est trop limité en calcul et la coordination y est trop lourde à gérer. Orca fournit déjà la plomberie : lancer des agents, les superviser, faire circuler leurs messages.
- La méthode est d'abord éprouvée sur un **projet de test**, puis étendue à tous les projets.

## 2. Principes

- **Simple is complex enough** : la méthode ajoute le moins de mécanique possible.
- **Les rôles ne connaissent pas la plomberie.** Un rôle reçoit un travail et rend un résultat ; il ignore la chaîne, les autres agents, le parallélisme, et qui tamponne après lui.
- **Les axes règlent la plomberie, jamais les rôles.** Changer les axes ne touche à aucun rôle.
- **Un harnais commun, hérité sans duplication.** Les règles vivent une fois, dans Ballet ; un projet n'ajoute que ce qui lui est propre.
- **L'auto peut toujours escalader vers moi**, sur des déclencheurs écrits.
- **Tout est tracé** dès la première version, pour pouvoir mesurer avant de lâcher la main.

## 3. Vocabulaire

Un terme par concept, et un seul nom partout : la doc, les skills, les clés de config et les commandes emploient les termes ballet (`/ballet:dramaturg`, `[roles.dancer]`). L'équivalent fonctionnel (PM, architecte, dev, validateur, coordinateur) n'apparaît que dans la **description** de chaque skill, pour qu'un agent le reconnaisse, et dans la table ci-dessous.

**Les personnages**

| Terme (et skill) | Équivalent fonctionnel | Ce qu'il fait |
|---|---|---|
| **Director** | — | Moi. Je cadre avec le Dramaturg, je tamponne en manuel et je reçois les escalades. |
| **Dramaturg** | PM | Cadre le périmètre fonctionnel, rédige l'issue et les specs. |
| **Choreographer** | architecte | Crée l'issue et son plan technique à partir d'une feature prête. |
| **Dancer** | dev | Exécute le plan. |
| **Critic** | validateur | Juge le travail et rend un verdict. |
| **Conductor** (`conductor`, `parallel-conductor`) | coordinateur | Enchaîne les rôles, répond à leurs questions et intègre leur travail. Il ne danse pas et ne compose pas. |

- **Rôle** : Dramaturg, Choreographer, Dancer ou Critic. Le Conductor n'est pas un rôle : il les fait jouer.
- **Worker** : l'instance d'agent (un CLI et un modèle) qu'Orca lance pour jouer un rôle.

**La chaîne et ses réglages**

- **Chaîne** : la suite fixe des phases d'une issue, en deux boucles :
  - **Workshop** : le cadrage (Director, Dramaturg, et le Choreographer en conseil, sans plan) ;
  - **Rehearsal** : plan, code et validation (Choreographer, Dancer, Critic), jusqu'à la **Premiere**, le merge de sa PR sur `main`.
- **Axes** (*Parameters*) : les réglages de la chaîne (qui cadre, qui tamponne, comment ça tourne).
- **Piece** : une combinaison nommée des axes, lancée par une commande. Le **répertoire** est la liste des Pieces.

**Le reste**

- **Profil projet** : `.ballet/config.toml`, dans le home du projet (repos, preuves, zones sensibles, seuils), que Ballet lit au lieu de la deviner. Le même fichier surcharge les défauts du plugin (routage, seuils).
- **Tampon** : la validation d'une phase, par un rôle (auto) ou par le Director (manuel).
- **Escalade** : le Conductor ou un worker s'arrête et demande au Director de décider.

**L'espace specs** (tenu par le Dramaturg, modèles dans `templates/` du plugin, en anglais)

- **Backlog** (`backlog.md`) : ce qui attend, en quatre sortes d'entrées :
  - **Opportunity** (`OPP-NNN`) : un problème pour quelqu'un, jamais une solution ;
  - **Feedback** : ce qu'un test a montré, en attente d'être classé (gap → bug, rectification → feature révisée, new need → opportunity) ;
  - **Bug** (`BUG-NNN`) : un écart entre la spec et le produit ;
  - **Task** (`TASK-NNN`) : un travail sans comportement visible nouveau.
- **Capability** (`CAP-NNN`) : le chapeau métier de plusieurs features ; le pourquoi, le signal de réussite, les règles métier transverses et les limites, sans critères.
- **Feature** (`FEAT-NNN`) : un comportement visible, quatre critères Gherkin au plus, une issue.
- **Issue** : l'issue GitHub, créée par le Choreographer à partir d'une feature prête (ou d'un bug, d'une tâche du backlog), avec son plan. Elle ne vit que sur GitHub, jamais dans l'espace specs.
- **Slice** (`FEAT-NNN.K`) : une part d'une feature trop grosse pour une seule session du Dancer, proposée par le Choreographer seulement si besoin. Chaque slice est une Rehearsal complète (sa branche, code, validation, preuve verte, merge de sa PR sur `main`) et livre au moins un critère entier de bout en bout (slice verticale, jamais une couche : API, puis client, puis écran) ; une slice sans critère n'est admise que pour le walking skeleton d'un repo vide, ou quand le plus petit critère seul dépasse le seuil. Le moins de slices possible, chacune estimée sous les deux tiers de `max_diff_lines`.
- **Branche de Rehearsal** (`rehearsal/<ID>`) : la branche courte d'une Rehearsal, dans son propre worktree, créée par le Conductor depuis `main` et supprimée après la Premiere. Le Choreographer et le Dancer y commitent, à tour de rôle ; la PR qui l'intègre porte la validation. Avec des slices, chacune a sa branche, partie de `main` après le merge de la précédente ; les ADR et les règles du plan voyagent avec la première.
- **Glossary** (`glossary.md`) : la langue du projet ; chaque terme avec son nom de code et son texte affiché.

**Langues.** Le plugin (skills, modèles, règles, README, messages des scripts) est en anglais ; le PRD, `opportunities.md`, `release.md` et les ADR restent en français tant que la méthode bouge. Le code est toujours en anglais. Les specs sont dans la langue `[project] specs_language` (anglais par défaut) ; le texte affiché par le produit reste dans la langue du produit, cité tel quel. La conversation avec le Director se fait dans sa langue.

## 4. La chaîne

**Workshop** (Dramaturg) → **Rehearsal** : plan (Choreographer) → code (Dancer) → validation (Critic) → **Premiere** : merge de la PR sur `main`

Elle est toujours la même. Seuls les axes changent la façon dont elle tourne.

En Workshop, le Choreographer peut être consulté, mais il ne rend son plan officiel qu'en Rehearsal.

## 5. Les rôles

### 5.1 Le contrat, identique pour tous

**Un rôle reçoit :**
- un espace de travail (`main` pour le Dramaturg, le worktree de la branche de Rehearsal pour les autres ; il n'a pas à savoir lequel) ;
- l'issue et le plan ;
- sa spec de rôle ;
- les règles à lire, communes et propres au projet ;
- la preuve attendue (build vert, tests…).

**Un rôle rend :**
- un résultat structuré ;
- ou une question, quand il est bloqué.

**Un rôle ne sait pas :**
- si le Director tamponne après lui ;
- si d'autres workers tournent en parallèle ;
- quel modèle tient les autres rôles ;
- qui répond à ses questions (le Conductor, le Dramaturg ou le Director).

**Un rôle ne pousse jamais.** Le Dancer commite ; l'intégration (push de la branche, PR, file de merge, attente du tampon du Director, merge) est de la plomberie, donc le travail du Conductor.

### 5.2 Les quatre rôles

- **Dramaturg** : cadre le périmètre fonctionnel et rédige l'issue et les specs (dans des fichiers, jamais sur GitHub directement). Répond aux questions de produit. Écrit dans l'espace specs du projet, nulle part ailleurs. Il travaille en amont du Conductor (Workshop interactif) ou lancé par lui (Workshop auto ou discovery).
- **Choreographer** : part d'une feature prête, lit le code, fixe les choix techniques et crée l'issue avec son plan, une section par repo (et les issues de slices si besoin), par le script GitHub. Pose ses questions au Dramaturg quand la feature a des manques, et reste éveillé en attendant la réponse. Rend un rapport au Conductor, qui le journalise. Seul à écrire les ADR (dossier `[project] adr`), les spikes (branches `spike/NN-slug`, jamais mergées) et les règles techniques du projet dans `AGENTS.md`. Pour le reste, lecture seule.
- **Dancer** : exécute sa section du plan en red → green → refactor, commite sur la branche de Rehearsal. Sur un refus, il reprend à partir de la review de la PR, qu'il lit sans y écrire. Preuve : la commande de preuve de son repo est verte. Écrit dans le code de son repo.
- **Critic** : relit le travail dans le worktree et rend un verdict. Lecture seule. Première ligne de sa réponse : `VERDICT: APPROVED`, `VERDICT: REJECTED` ou `VERDICT: ESCALATE`, puis les preuves et **tous** les points bloquants, en un seul lot (jamais remarque par remarque), et des notes optionnelles que le Dancer n'est pas tenu de suivre. Le Conductor le publie en une review de la PR. Il ne merge pas : juger et intégrer restent séparés.

Chaque spec de rôle est autonome : la cible, le changement, ce que le rôle peut éditer, la preuve attendue, et si un code de sortie non nul signifie un échec.

### 5.3 Garde-fous : chacun reste dans son périmètre

Une consigne ne suffit pas : un agent peut la lire et la transgresser quand même. Le périmètre est donc tenu par trois couches, de la plus souple à la plus dure. **La dernière est une politique déterministe**, appliquée sans jugement de modèle et identique pour tous les CLI.

**Le périmètre est fixé par rôle, dans Ballet, jamais par tâche :**
- **Dancer** : écrit dans le code de son repo, hors espace specs et hors zones interdites. Le plan ne restreint pas les fichiers qu'il touche ;
- **Dramaturg** : écrit dans l'**espace specs** (backlog, capabilities, features, glossaire…), déclaré dans le profil projet : un repo de specs, ou un dossier dans un repo unique. Jamais dans le code ;
- **Choreographer** : écrit seulement les ADR (dossier `[project] adr`) et `AGENTS.md`, sur la branche de Rehearsal, et les spikes (code jetable et compte rendu `spikes/NN-slug.md`, sur une branche `spike/NN-slug` jamais mergée). `AGENTS.md` lui sert à imposer une règle technique (ses sections projet, jamais le bloc Ballet). Quand il répond à une question du Dancer, il commite dans le même worktree pendant que le Dancer attend : la règle voyage dans la PR avec le code qui la suit. Il crée l'issue avec son plan, et les issues de slices, **par le script GitHub uniquement**, puis rend son rapport au Conductor ;
- **Critic** : lecture seule. Il **rend** son verdict ; c'est le Conductor qui le publie sur la PR ;
- **Conductor** : ne touche pas au code ; il publie sur GitHub ce que les rôles lui rendent, et il intègre, toujours par le script GitHub (section 5.4).

**Zones interdites à tous les rôles**, sauf tâche explicitement dédiée et validée par le Director :
- le harnais : `AGENTS.md` (sauf pour le Choreographer), `CLAUDE.md`, `.claude/`, `.agents/`, `.ballet/`, la configuration des CLI, Ballet lui-même ;
- les ADR, sauf pour le Choreographer ;
- les zones sensibles déclarées dans le profil projet (contrat d'API, sécurité…) ;
- les fichiers de CI et les hooks git ;
- l'historique git : pas de réécriture, pas de force push, pas de suppression de branche.

**Couche 1 — la consigne.** La spec de rôle dit le périmètre et les zones interdites. Un Dancer qui a besoin d'une zone interdite **ne la touche pas** : il le signale au Conductor.

**Couche 2 — les permissions du CLI, quand il en a.** Le worker est lancé avec les droits les plus étroits que son CLI sait imposer :
- Critic en lecture seule (mode plan ou agent en lecture seule) ; comme il n'écrit rien, pas même l'issue, ce mode lui suffit ;
- Choreographer limité aux ADR, à `AGENTS.md` et à ses branches de spike ;
- Dramaturg limité à l'espace specs ;
- Dancer limité à son repo, sans accès en dehors du dossier de travail.

Ces réglages dépendent de chaque CLI (Claude Code : permissions ; Mistral Vibe : agents personnalisés avec outils et permissions, `outside_workdir = "deny"` ; Grok : à étudier). Ce ne sont pas des hooks, mais leur portée réelle est à vérifier CLI par CLI. Ballet ne compte pas dessus seul.

**Couche 3 — la politique, déterministe.** C'est la couche qui fait foi.
- C'est **un script de Ballet, pas un modèle** : il prend le rôle, l'état du repo avant et après, les zones interdites (défauts de Ballet et profil projet), et rend un code de sortie et la liste des violations.
- Le Conductor l'exécute après chaque rôle et **applique son résultat tel quel** : il ne l'interprète pas, ne le discute pas, ne passe pas outre.
- Ce qu'il vérifie :
  - **Critic** : `HEAD` n'a pas bougé et l'arbre de travail est propre (`git status --porcelain` vide) ;
  - **Choreographer** : sur la branche de Rehearsal, tous les fichiers modifiés sont dans le dossier des ADR ou sont `AGENTS.md` ; seules des branches `spike/*` ont été créées ; il est revenu sur la branche de Rehearsal ; l'arbre de travail est propre ; pas de réécriture d'historique ;
  - **Dramaturg** : tous les fichiers modifiés sont dans l'espace specs, aucun dans une zone interdite ; l'arbre de travail est propre ; pas de réécriture d'historique ;
  - **Dancer** : il est resté sur la branche de Rehearsal ; aucun fichier modifié par ses commits n'est dans l'espace specs, dans le dossier des ADR ni dans une zone interdite ; l'arbre de travail est propre ; le nouveau `HEAD` descend de l'ancien (pas de réécriture d'historique) ; aucune branche ni aucun tag créé ou supprimé ; aucun test présent sur `main` n'a disparu ni changé de nom (reconnu par son nom : `it`/`test` en JS et TS, `#[test]` en Rust, `def test_` en Python, `Scenario:` en Gherkin). Le corps d'un test existant modifié reste au Critic : au premier run, chaque Rehearsal a retouché les imports d'un fichier de test, une règle à la ligne aurait tout bloqué.
  - **v0 (0.15.0)** : `scripts/ballet_policy.py`, appelé par le Conductor au rapport du Dancer (avant le push), au verdict du Critic (avant sa publication), au plan et à chaque réponse du Choreographer. Ses données vivent dans `[policy]` (défauts du plugin, surchargés par le projet). Le périmètre de chaque rôle, `[policy.roles.<rôle>]` : un chemin est permis s'il est dans `writes` ou `extra_writes` et hors de `except` et `extra_except` (`except` l'emporte), plus `branches`, les branches qu'il peut créer. `writes` et `except` portent la méthode, qu'un projet peut remplacer ; `extra_writes` et `extra_except`, vides par défaut, l'étendent sans la recopier (donner `docs/*` au Choreographer, interdire `migrations/*` au Dancer). `@specs`, `@adr`, `@forbidden` et `@sensitive` y nomment l'espace specs, le dossier des ADR, `forbidden_zones` et `sensitive_zones`. Les tests se reconnaissent par `test_names` (par langage : extensions et motif du nom ; un projet ajoute le sien par `[policy.test_names.<langage>]`). Une config qui laisse un rôle écrire `.ballet/config.toml` est refusée. Le Dramaturg consulté pendant une Rehearsal commite sur la branche de Rehearsal ; ses commits, comme ceux du Choreographer, sont vérifiés à sa réponse et ne comptent pas contre le Dancer. Le contrôle de l'état GitHub n'y est pas encore. La planification d'une feature est un passage du Choreographer comme un autre, vérifié à son rapport ; ses commits restent les siens (`owned`) quand la première slice prend son worktree (0.19.0).
  - **tous les rôles** : l'état GitHub de l'issue et de la PR (corps, libellés, commentaires, reviews, état) est identique avant et après leur passage ; seule exception, le Choreographer, qui crée l'issue de sa feature et ses slices (liées à la parente) et peut réécrire leur section `## Plan`.
- Les zones interdites sont des motifs de chemins (globs), pour que la vérification reste mécanique.
- **Un commit appartient au rôle pendant le passage duquel il est apparu** : le Choreographer et le Dancer partagent la branche de Rehearsal, mais jamais en même temps, et l'état avant et après chaque passage suffit à les départager.

**Une violation n'est jamais intégrée.** Le Conductor ne pousse pas ; il renvoie le travail au rôle avec la liste des violations, une fois. À la deuxième violation, il escalade vers le Director. Toute violation est journalisée.

### 5.4 GitHub : un seul point de passage

**Toute interaction avec GitHub passe par un script déterministe de Ballet** (`scripts/ballet_github.py`). Le Conductor l'appelle ; le Choreographer aussi, pour ses seules opérations (créer l'issue, créer une slice, lire une issue, réécrire son plan) ; le Dancer, seulement pour lire son issue et sa PR. Aucun rôle n'appelle `gh`, l'API GitHub ou `git push` directement.

- **Le script expose une liste fermée d'opérations**, chacune avec ses entrées vérifiées :
  - lire une issue ;
  - créer une issue (Choreographer) ;
  - créer une issue de slice, liée à sa parente (Choreographer) ;
  - réécrire la section `## Plan` d'une issue (Choreographer) ;
  - cocher une tâche du plan ;
  - commenter l'issue (échanges entre rôles, escalade, rapport final) ;
  - poser ou retirer un libellé ;
  - pousser la branche de Rehearsal ;
  - ouvrir la PR, liée à l'issue ;
  - lire une PR et ses reviews (Conductor, Dancer) ;
  - publier une review de la PR (verdict du Critic) et la commenter (rapport du Dancer) ;
  - merger la PR par rebase (la Premiere) après une politique verte, une CI verte et le tampon de la phase, puis supprimer sa branche ; le verdict qui fait foi est le libellé de la PR (`ballet:approved`, `ballet:rejected`, `ballet:escalated`) : le Conductor pose celui du Critic, le Director tranche une escalade en posant le sien, et le merge exige `ballet:approved` posé après le dernier commit ;
  - fermer l'issue.
- **Jamais de push direct sur `main`** : `main` ne bouge que par le merge d'une PR.
- **Aucune opération libre** : pas de commande `gh` arbitraire, pas de suppression, pas de modification des réglages du repo.
- **Le Conductor décide quand appeler une opération, jamais comment elle s'exécute.**
- **Chaque appel est journalisé** (opération, entrées, résultat), comme les transitions.
- **Les rôles produisent, le script publie :** le Choreographer publie lui-même l'issue et ses slices, puis rend son rapport au Conductor, qui le journalise ; le Critic rend son verdict, le Conductor le publie.
- **Garde-fous :** couche 2, les workers sont lancés sans accès à `gh` ni au jeton GitHub quand le CLI le permet ; couche 3, la politique vérifie que l'état GitHub de l'issue n'a pas bougé pendant le passage d'un rôle.

## 6. Les axes

**Workshop** — qui cadre :
- **interactif** : le Director et le Dramaturg ;
- **auto** : le Dramaturg cadre seul une demande, un bug, un retour ou une issue GitHub ;
- **discovery** : le Dramaturg choisit seul dans le backlog et les opportunités.

**Plan** — qui tamponne le plan du Choreographer :
- **auto** ;
- **manuel** : le Director.

**Validation** — qui tamponne le code avant la Premiere :
- **auto** : le Critic tamponne ;
- **manuel** : le Director tamponne, avec le rapport du Critic sous les yeux.

**Exécution** — comment la chaîne tourne :
- **séquentielle** : une Rehearsal ouverte à la fois, dans son worktree, une PR à la fois ;
- **parallèle** : plusieurs Rehearsals ouvertes, chacune dans son worktree, une file de merge.

### 6.1 L'escalade, contrat de l'auto

Toute phase en auto peut escalader vers le Director. Les déclencheurs par défaut :

**Côté Critic**
- deux refus de suite (le ping-pong ne converge pas) ;
- un doute sur son propre verdict (`VERDICT: ESCALATE`) ;
- un désaccord persistant avec le Dancer.

**Côté changement**
- il sort du périmètre fonctionnel de l'issue ;
- un rôle viole la politique une deuxième fois (section 5.3) ;
- il touche une zone sensible déclarée par le projet (contrat d'API, sécurité, décisions d'architecture, harnais…) ;
- il dépasse une taille de diff fixée, comptée par le script (lignes changées hors `diff_exclude`) et non par le Critic ; hors mode strict, la PR est seulement marquée `ballet:oversized` ; en mode strict, l'escalade précède le Critic, et le Director la lève par `ballet:size-accepted` ;
- il modifie ou supprime un test existant au lieu d'en ajouter.

**Côté exécution**
- la preuve du repo, lancée par le script à chaque rapport du Dancer, reste rouge au-delà du plafond d'allers-retours, ou dépasse `proof_timeout_seconds` ;
- le test de mutation, lancé par le script après la preuve, reste rouge au-delà du plafond d'allers-retours, ou dépasse `[mutation] timeout_seconds` ;
- un build instable (vert puis rouge sans changement) ;
- en parallèle, un conflit de merge que le Dancer n'a pas résolu proprement.

La liste est commune ; les seuils et les zones sensibles vont dans `.ballet/config.toml`.

**Ce que fait une escalade :**
- en séquentiel, la chaîne attend le tampon du Director ;
- en parallèle, seule la tâche escaladée sort du train de merge, les autres continuent ;
- le Director reçoit le verdict, le motif et le diff, de quoi décider sans rouvrir la session ;
- chaque escalade est journalisée avec son motif, pour savoir quels déclencheurs relâcher.

Attendre le tampon du Director n'est jamais un échec : le Conductor prévient le Director et attend.

## 7. Le Conductor

- **L'axe Exécution choisit le skill du Conductor** :
  - `conductor` : séquentiel, une Rehearsal ouverte à la fois (sa branche, son worktree, sa PR) ;
  - `parallel-conductor` : plusieurs Rehearsals ouvertes, le même mécanisme, plus une file de merge (plus tard, hors V1) :
    - il ne lance en parallèle que des Rehearsals indépendantes : pas de `needs` entre leurs repos, pas de slices d'une même feature ;
    - l'ordre de merge : d'abord les dépendances (`needs`, ordre des slices), puis la première PR prête (verdict, CI, tampon) ;
    - après chaque merge, il rebase les autres branches ouvertes sur `main` ; un conflit retourne au Dancer dans sa session, qui le résout et repasse sa preuve ; le Critic relit la résolution avant le merge ;
    - un conflit mal résolu ou une deuxième résolution ratée : escalade (section 6.1), seule cette Rehearsal sort de la file.
- **Le plan et la validation** sont ses points d'arrêt : il continue seul (auto, sauf escalade) ou il attend le Director (manuel).
- **Le Workshop dit d'où il part** :
  - interactif : le Workshop se fait avant lui, il démarre sur une issue prête ;
  - auto : il lance d'abord un Dramaturg qui cadre la demande ;
  - discovery : il lance d'abord un Dramaturg qui choisit quoi faire.
- Les deux skills font jouer **les mêmes rôles**.
- Le Conductor ne code pas et n'écrit pas de plan : il lance, répond, juge les preuves et intègre.
- Un plafond d'allers-retours Dancer ↔ Critic (2 par défaut) existe dès le séquentiel.
- **La preuve ne se croit pas sur parole** : à chaque rapport du Dancer, après la politique et avant le push, le script lance lui-même la preuve du repo dans le worktree. Rouge (ou un worktree sali par la preuve), rien n'est poussé, le Critic n'est pas mobilisé : le Dancer reprend avec la fin de la sortie. Au-delà de `max_round_trips` preuves rouges, ou trop longue, escalade (0.24.0).
- **Le test de mutation, après la preuve** : Ballet porte la méthode, le projet l'outil. Le projet fige l'outil, sa config (où s'excluent les équivalents, chacun avec sa raison) et déclare une entrée par outil dans son profil (`[[repos.<repo>.mutation]]`) ; Ballet calcule le diff de la branche contre son ancêtre commun avec `origin/main`, le passe à chaque outil (`{diff}`, `{files}`, `{ranges}`), et le code de sortie décide. Trop long pour un appel du Conductor, il part en arrière-plan et le réveille par Orca à sa fin. Rouge : rien n'est poussé, le Critic n'est pas mobilisé, le Dancer reprend avec les survivants ; au-delà de `max_round_trips`, ou d'une heure, escalade. Un survivant se tue par un test unitaire ; le Critic juge chaque exclusion (`ballet:tdd`). `[mutation] enabled = false` coupe le nœud sans retirer les entrées (0.25.0).
- Rien de destructeur ni de sortant hors du repo sans l'accord du Director.

### 7.1 Le répertoire

- `hybrid-track` = Workshop interactif · plan manuel (`--plan review`, défaut) ou auto (`--plan auto`) · validation auto · séquentielle
- `auto-track` = Workshop auto · plan auto · validation auto · séquentielle
- `auto-track-discovery` = Workshop discovery · plan manuel · validation manuelle · séquentielle (pour commencer)
- `hybrid-parallel` = Workshop interactif · plan auto · validation auto · parallèle

Une Piece n'est pas un skill de plus : c'est un raccourci qui appelle le bon skill du Conductor avec ses paramètres. Toute autre combinaison reste possible sans rien écrire.

**Piece v0 : `hybrid-track`.** Le Director cadre avec le Dramaturg (Workshop interactif), puis **déclenche en personne le Conductor** (`/ballet:hybrid-track`) : ce geste est son tampon de Workshop, rien ne part automatiquement à la fin du Workshop. Ensuite la Rehearsal (plan, code, validation) s'enchaîne en **auto** jusqu'à la Premiere, sauf escalade. Le Conductor merge la PR dès que le Critic rend `APPROVED`, que la politique et la CI sont vertes.

**Le flow séquentiel complet (0.18.0 à 0.21.0).** La Piece prend une **file** : une issue (`#12`), plusieurs (`#12 #13 #14`), ou des features prêtes (`FEAT-002 FEAT-003`). Tout est séquentiel : une seule Rehearsal ouverte à la fois, un seul worker actif, l'ordre de la commande fait foi (pas de dépendances entre features). À la Premiere d'une Rehearsal, le script ouvre lui-même la suivante, depuis `main` : une feature est donc planifiée sur le vrai `main`, après la dernière Premiere de la précédente. La file vit dans `.ballet/run/queue.json` ; une escalade la met en pause, `resume` reprend la Rehearsal, puis la file.
- **Une feature** ouvre une Rehearsal de **planification**, dont le seul rôle est le Choreographer, en **mode auto** : il tranche, découpe et publie sans attendre de oui ; les questions de produit vont au Dramaturg, ce qu'il ne peut pas trancher au Director (escalade). En Workshop, il reste interactif. Une issue sans plan suit le même chemin.
- **À son rapport**, le script lit sur GitHub l'issue et ses slices (`Part of #N` en première ligne) et les place en tête de file ; une issue sans slices entre seule.
- **Les ADR** du Choreographer (et `AGENTS.md`) partent avec la première slice, ou l'issue unique : le worktree de la planification devient le sien (sa branche est renommée), ses commits restent au Choreographer pour la politique et arrivent sur `main` au premier merge. Pas de PR d'ADR à part.
- **Le plan** : en `--plan review` (défaut, `[escalation] plan_approval = true`), la file s'arrête après la publication ; le Director pose `ballet:plan-approved` sur l'issue planifiée, puis `resume`. En `--plan auto`, on enchaîne.

On part en auto dès le début, pour mesurer la qualité du Critic grâce au journal (refus, allers-retours, builds rouges, merges à corriger après coup). Les garde-fous restent actifs : déclencheurs d'escalade, plafond d'allers-retours, politique déterministe. Des Pieces avec **tampon manuel** (plan, validation) viendront plus tard, au fil des besoins.

## 8. La communication entre workers

- **En étoile** : tout passe par le Conductor. Les workers ne se parlent pas entre eux. Le Conductor sait qui a demandé quoi, peut répondre lui-même, arbitre et trace.
- **Primitives Orca** : un worker pose une question avec `ask` et termine avec `worker_done` ; le Conductor répond avec `reply` et écrit à un worker avec `send`.
- **Un seul format de message**, pour tous les échanges (`templates/message.md`) : une première ligne JSON, l'en-tête (`from`, `to`, `type`, `subject`, `round`), lue par le Conductor avec la bibliothèque standard ; puis le corps en Markdown, jamais échappé, pour les agents et le Director. Un en-tête qui n'est pas du JSON valide est renvoyé. Types : `question`, `answer`, `report`, `verdict`, `escalation`. Le Conductor ne lit que l'en-tête : il route sur `to`, compte les tours par sujet et par paire de rôles, et escalade vers le Director au-delà de `[escalation] max_exchange_rounds` (3 par défaut).
- **Qui répond** : produit → Dramaturg, technique → Choreographer, hors cadre → Director.
- **Un plan modifié retourne toujours dans l'issue**, jamais seulement dans les messages, avec sa ligne d'amendement (round, décision, raison).
- **Tous les échanges sont publiés** : le Conductor commente l'issue avec chaque question et chaque réponse (le message entier, en-tête compris), et la PR avec chaque rapport du Dancer ; le verdict du Critic y est une review. La trace complète reste sur GitHub, pour l'analyse (section 12).
- En parallèle, un Dancer qui découvre une collision avec un autre Dancer le signale au Conductor, qui gère l'ordre de merge.
- Le Dramaturg consulté pendant la Rehearsal est **éphémère par défaut** : lancé à la demande avec l'issue et la question, il répond à partir de l'issue et des specs. Si sa réponse change le périmètre, il met l'issue ou les specs à jour.
- **Choreographer → Dramaturg** : si la feature a des manques (cas oublié, contradiction, critère flou, mot absent du glossaire, découpage trop gros), le Choreographer envoie une `question` au Dramaturg, points numérotés avec sa recommandation, et **reste éveillé** pour garder son contexte. Le Dramaturg rend une `answer`, point par point : une réponse simple, ou une modification déjà commitée dans les specs (commit et fichiers nommés, sans le diff ; le Choreographer relit les specs). Un manque purement technique reste au Choreographer.

## 9. Les agents

- Orca sait lancer, entre autres : `claude`, `grok`, `mistral-vibe`, `codex`, `opencode`, `gemini-cli`, `kimi`.
- **Le routage par rôle** associe à chaque rôle un **CLI** et un **modèle**. Il ne vit jamais dans les rôles.
- **Les défauts** sont dans le `config.toml` du plugin. **Un projet les surcharge** dans `.ballet/config.toml` (section `[roles.<rôle>]`, où `<rôle>` est le nom du skill : `dramaturg`, `choreographer`, `dancer`, `critic`). Le Conductor fusionne clé par clé : ce qui n'est pas surchargé hérite. Changer de modèle modifie une ligne.
- **Vérifié au lancement, sur la configuration fusionnée** : la règle « Critic ≠ Dancer » et la capacité du CLI à lancer le modèle demandé. Sinon le Conductor refuse de démarrer.
- Départ : tous les rôles sur Claude (Choreographer et Critic en Opus, Dancer en Sonnet). Cible : Dancer Mistral, Critic Grok ou Claude.
- **Seule règle : Critic ≠ Dancer**, pour que leurs angles morts ne se recouvrent pas.
- Le Dancer commence sur Claude comme référence ; les mêmes issues sont ensuite rejouées avec Mistral et comparées (refus du Critic, allers-retours, builds rouges).

## 10. Le harnais commun

### 10.1 Ballet est un plugin

- Le repo `ballet` est **la source** d'un plugin Claude Code, installé une fois au niveau utilisateur. On modifie la méthode dans son repo, on la versionne, chaque projet récupère la mise à jour.
- Les skills s'appellent `/ballet:<skill>` : `/ballet:dramaturg`, `/ballet:hybrid-track #12`, `/ballet:init-project`.

**Le repo Ballet contient :**
- les règles communes : tdd, ddd, bdd, clean code, trunk-based… ;
- les skills de rôles : `dramaturg`, `choreographer`, `dancer`, `critic`, chacun avec son équivalent fonctionnel dans sa description ;
- les skills du Conductor : `conductor`, puis `parallel-conductor` ;
- le répertoire des Pieces ;
- les réglages par défaut (`config.toml`) : routage (CLI et modèle par rôle), déclencheurs d'escalade, plafonds ;
- le modèle de `.ballet/config.toml` et le skill d'amorçage `init-project` ;
- les scripts déterministes (config, politique, GitHub) : **Python**, dernière version, bibliothèque standard uniquement. Un script a un seul objectif ; ses fonctions publiques se lisent comme une histoire, à un niveau d'abstraction élevé et constant, et les détails techniques descendent dans des fonctions privées ;
- le format du journal d'événements ;
- la doc et les décisions de la méthode ;
- le manifeste du plugin.

### 10.2 Ce que lit chaque CLI (vérifié le 11 novembre 2026)

- **Claude Code** : son plugin, ses skills, `CLAUDE.md`.
- **Grok** : nativement les skills, agents et plugins de Claude Code (`.claude/skills`, `.claude/agents`, `.claude/plugins`, plugins installés, marketplaces), `CLAUDE.md`, `.mcp.json`, les hooks. Source : README du CLI Grok, section « Claude Code Compatibility ».
- **Mistral Vibe** : le standard Agent Skills (`.agents/skills`, `.vibe/skills`, `~/.agents/skills`, `skill_paths`), `AGENTS.md` (pas `CLAUDE.md`), dans les dossiers de confiance. Il adapte un plugin Claude Code placé dans `~/.vibe/plugins`, mais **seulement ses skills et ses serveurs MCP** (ni hooks, ni agents). Sources : docs.mistral.ai, pages Skills, Plugins et Agents.

**Conséquences :**
- un seul plugin sert les trois CLI ;
- les règles du projet vont dans `AGENTS.md`, que `CLAUDE.md` importe (`@AGENTS.md`) ;
- **pas de hooks dans Ballet** : tout garde-fou passe par le Conductor ou par la preuve. Les permissions propres à chaque CLI ne sont qu'une couche en plus (section 5.3).

### 10.3 Découvert n'est pas appliqué

Un skill est chargé à la demande, selon sa description : rien ne garantit qu'un agent pense à charger `tdd` avant de coder. Les règles sont rendues obligatoires à trois endroits :
- chaque skill de rôle dit quelles règles charger ;
- le profil projet dit quelles règles communes s'appliquent ;
- le Conductor les nomme dans la spec du worker.

### 10.4 Ce qui reste dans chaque projet

- `AGENTS.md` : les règles propres au domaine ;
- `CLAUDE.md`, qui importe `AGENTS.md` ;
- les skills propres au projet dans `.claude/skills/`, avec `.agents/skills` lié vers ce dossier pour Mistral Vibe (créé par `init-project`) ;
- `.ballet/config.toml` : le profil du projet et ses surcharges des défauts ;
- les issues et les plans.

**Une règle du projet l'emporte sur une règle commune** (un projet client qui impose sa convention de commit, par exemple).

### 10.5 Le profil projet : `.ballet/config.toml`

Il vit dans le **home du projet** (repo unique, ou repo de specs en multi-repos). C'est un fichier TOML, pas une section de `AGENTS.md` : des scripts déterministes le lisent (politique, GitHub), et les rôles n'y ont pas accès en écriture. Il absorbe les structures différentes : un seul repo (code et specs ensemble) ou un repo de specs avec plusieurs repos de code. Il contient :
- l'**espace specs** où écrit le Dramaturg (repo ou dossier), et où vivent les issues et les plans ;
- les repos, chacun nommé librement par le projet, avec son chemin, sa commande de preuve et ses dépendances (`needs`) : un repo peut en attendre d'autres (par exemple une passerelle qui consomme un contrat généré par un service) ;
- les règles communes héritées ;
- les zones sensibles et les seuils d'escalade ;
- les surcharges de routage des rôles (section `[roles.<rôle>]`).

Les défauts viennent du `config.toml` du plugin ; le fichier projet les surcharge clé par clé.

- **Facultatif pour les surcharges** (routage, seuils) : sans fichier, les défauts du plugin s'appliquent.
- **Obligatoire pour les champs projet** (repos, preuve) : sans eux, le Conductor refuse de démarrer et renvoie vers `/ballet:init-project`.
- **Vérifié au lancement** : un cycle dans les `needs`, ou un `needs` qui pointe vers un repo inconnu, fait refuser le démarrage.

**Structure.** Le schéma exact est fixé dans `docs/ADR/0003-*` (clé `model` facultative par rôle, en plus de `cli`).

Les défauts du plugin (extrait) :

```toml
# config.toml du plugin Ballet

[roles.dramaturg]
cli = "claude"

[roles.choreographer]
cli = "claude"
model = "opus"

[roles.dancer]
cli = "claude"
model = "sonnet"          # référence de départ, puis Mistral (section 9)

[roles.critic]
cli = "claude"
model = "opus"            # Critic ≠ Dancer : modèle différent

[escalation]
max_round_trips = 2       # allers-retours Dancer ↔ Critic
```

Un projet multi-repos :

```toml
# .ballet/config.toml, à la racine du home du projet

[project]
specs = "specs/"                       # espace du Dramaturg
rules = ["tdd", "ddd", "clean-code", "trunk-based"]

[repos.billing]
path = "../billing"
proof = "make test"

[repos.auth]
path = "../auth"
proof = "make test"

[repos.gateway]
path = "../gateway"
proof = "npm test"
needs = ["billing", "auth"]            # lancé après eux

[repos.web]
path = "../web"
proof = "npm test"
needs = ["gateway"]

[[repos.billing.mutation]]              # le test de mutation de ce repo, après la preuve (un outil par entrée)
name = "cargo-mutants"
command = "mise exec -- cargo mutants --in-diff {diff}"   # {diff} un fichier, {files}, {ranges} (`fichier:début-fin`)
config = ".cargo/mutants.toml"           # où s'excluent les équivalents, avec leur raison
report = { path = "mutants.out/outcomes.json", format = "cargo-mutants" }

[policy]
sensitive_zones = ["*/contract/*"]     # globs, valables dans tous les repos (`*` traverse les `/`)

[policy.roles.choreographer]
extra_writes = ["docs/*"]              # s'ajoute à la méthode (ADR, AGENTS.md), sans la recopier

[policy.test_names.go]                 # un langage de plus : la politique y reconnaît les tests par leur nom
extensions = [".go"]
pattern = 'func (Test\w+)'

[escalation]
max_diff_lines = 400
max_diff_strict = true                   # escalade avant le Critic au-delà du seuil (défaut : false)
ci_wait_seconds = 480                    # la Premiere attend une CI en cours jusque-là (défaut : 480, sous 600)
proof_timeout_seconds = 420              # la preuve lancée par le script au rapport du Dancer (défaut : 420, sous 600)
plan_approval = false                    # le plan du Choreographer part sans `ballet:plan-approved` (défaut : true)
diff_exclude = ["*.lock", "**/generated/**"]

[mutation]
enabled = true                           # false : le nœud de mutation est sauté, les entrées restent (défaut : true)
timeout_seconds = 3600                   # le budget de tous les outils, en arrière-plan (défaut : 3600)

[roles.dancer]                            # surcharge : le reste hérite des défauts
cli = "mistral-vibe"
```

En mono-repo, une seule entrée `[repos.<nom>]` avec `path = "."` et sans `needs`.

## 11. Lancer Ballet

**Tout part du home du projet** (son repo unique ou son repo de specs), dans un workspace Orca :

1. `/ballet:dramaturg` : le Director cadre avec le Dramaturg (Workshop), jusqu'à une feature prête dans l'espace specs.
2. `/ballet:hybrid-track FEAT-NNN` : la Piece appelle `conductor` ; le Conductor lance le Choreographer, qui crée l'issue et son plan (#12, et ses slices), puis enchaîne les Rehearsals. Une issue déjà créée se lance aussi : `/ballet:hybrid-track #12` ; plusieurs, en file : `/ballet:hybrid-track #12 #13`, `/ballet:hybrid-track FEAT-002 FEAT-003` ; `--plan auto` pour se passer de la validation du plan.
3. Le Conductor lit le profil et lance Choreographer, Dancer et Critic dans les bons repos (`orca orchestration worker-start --worktree path:<repo>`).

Autres entrées :
- `/ballet:auto-track "<besoin, bug ou retour>"` : le Dramaturg cadre seul, la Rehearsal suit ;
- le Workshop discovery : à déclencher à heure fixe (automations Orca, à étudier).

Pourquoi le home du projet : le Dramaturg et le Conductor y voient le contexte sans effort, Mistral Vibe n'y charge `AGENTS.md` et les skills que dans un dossier de confiance, et une session y correspond à un projet.

## 12. Le monitoring

- **Sur GitHub**, la trace des échanges : l'issue (plan, amendements, questions et réponses) et la PR (rapports du Dancer, verdicts du Critic).
- **Dès la V1**, le Conductor écrit un événement par transition (JSON lines) : run, issue, phase, rôle, CLI et modèle, début, fin, résultat, allers-retours, escalades et leur motif.
- **Concept en place** : la Scène (`scripts/ballet_stage.py`, page `stage/index.html`), une page locale en lecture seule, par projet, qui lit `.ballet/run/`, la distribution du profil et le titre des issues. Volontairement basique : par projet, les Rehearsals en cours et passées, le rôle qui a la main, et le fil du journal (ce que le Conductor remet à chaque worker, les messages reçus en entier, les pas du script), mis à jour en direct. C'est un outil d'observation pour se forger des convictions, pas un livrable de la V1 (§14).
- **Plus tard**, un vrai tableau de bord par-dessus ces données, à la manière de ce qui était prévu pour Nightshift. Sources complémentaires côté Orca : `orca search` dans les sessions, `worker-list`, `inbox`, hooks de statut des agents.
- Il sert à piloter, à **comparer les modèles par rôle**, et à décider quand passer une phase de manuel à auto.

## 13. Contraintes et limites connues

- **Orca tourne en local** : Mac allumé et Orca ouvert, sinon rien n'avance. Les serveurs appariés d'Orca (`--on <environment>`) sont à étudier.
- **Branches courtes** : une branche de Rehearsal vit le temps d'une issue ; `main` ne reçoit que des PR validées, mergées une par une par le Conductor.
- **Deux workers ne tournent jamais en même temps sur le même worktree.**
- **Workshop discovery** : c'est le mode le plus risqué ; il commence en mode propositions (issues que le Director valide) avant d'enchaîner seul, et seulement pour certains types de travail.

## 14. Hors périmètre de la V1

- `parallel-conductor` et la file de merge ;
- le Workshop discovery autonome ;
- le tableau de bord de monitoring abouti (le journal est dans la V1 ; la Scène n'en est que le concept, voir §12) ;
- un cockpit dans le repo Ballet pour piloter plusieurs projets depuis un seul endroit (registre des projets, discovery entre projets) ;
- la migration de Flownest.

## 15. Plan de test

1. Installer Mistral Vibe. Vérifier, CLI par CLI (Claude, Grok, Mistral), qu'un worker Orca reçoit une spec, voit les skills du plugin et sait appeler `ask` et `worker_done`, sur une tâche bidon.
2. Construire Ballet : règles communes, rôles, routage, modèle de `.ballet/config.toml`, `init-project`, manifeste du plugin. Vérifier l'installation dans les trois CLI.
3. `conductor` séquentiel, Workshop interactif, plan et validation en auto (Piece v0 `hybrid-track`), avec le journal d'événements.
   Projet de test : `../antimurphy` (mono-repo). Il lui faut un remote GitHub avant cette étape.
4. Rejouer les mêmes issues avec un Dancer Claude puis un Dancer Mistral, et comparer.
5. Workshop auto (`auto-track`).
6. Un projet multi-repos (specs + plusieurs repos de code), pour éprouver le profil.
7. `parallel-conductor` (`hybrid-parallel`).
8. Workshop discovery, en propositions d'abord.
9. Migrer Flownest.

À chaque étape, noter ce qui casse avant de passer à la suivante.

## 16. Ce que la migration de Flownest changera

- Les règles génériques de Flownest (tdd, ddd, clean code, trunk-based) montent dans Ballet ; le domaine (glossaire, invariants du moteur) reste dans le projet.
- `/code` pousse aujourd'hui sur `main` après chaque tâche : dans Ballet, le push sort du Dancer et passe au Conductor.
- `/feature`, `/plan`, `/code`, `/slice` sont remplacés par les rôles et les Pieces de Ballet.

## 17. Questions ouvertes

Tranchées par le spike 1 et l'étape 2 : voir `docs/ADR/0001-*` à `0003-*`.

- La marketplace du plugin au-delà du test (pendant le test : chemin local).
- Un worker Orca peut-il écrire directement à un autre worker ? (La méthode n'en dépend pas : elle passe par le Conductor.)
- Les automations Orca suffisent-elles pour déclencher le Workshop discovery ?
- Utiliser les Tasks Orca (`run-create`, `task-create --deps`) ou enchaîner les `worker-start` à la main : on commence sans.
- Le Dramaturg consulté pendant la Rehearsal reste-t-il éphémère, ou devient-il persistant ?
- Le format exact du journal d'événements.
- Quelles permissions chaque CLI sait réellement imposer à un worker lancé par Orca (lecture seule, limite au dossier de travail), et comment Orca les lui passe.
- ~~La source de vérité d'une issue~~ : tranché, il n'y a plus de brouillon ; le Choreographer crée l'issue à partir de la feature, et l'issue (plan compris) ne vit que sur GitHub.
- Qui pousse les commits du Dramaturg (specs, sur `main`) quand l'espace specs est dans le repo de code : une PR de specs, ou le Conductor au début de la Rehearsal ?
- Un repo sans CI : la Premiere se contente-t-elle de la preuve locale ?
- Signer les commits par rôle (une clé par rôle) n'a de sens qu'avec une isolation par l'OS (un utilisateur ou un bac à sable par rôle) : sous le même utilisateur, le Dancer peut lire la clé du Choreographer. Même chantier que la ligne suivante.
- Comment priver un worker de `gh` et du jeton GitHub quand Orca le lance (variables d'environnement, permissions du CLI).
