# Ballet — PRD

> Méthode commune à tous mes projets pour faire travailler des agents de code (Claude, Grok, Mistral…) en chaîne, sur la plomberie d'Orca.
> Statut : cadrage, rien n'est construit. Version du 14 novembre 2026.

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
| **Choreographer** | architecte | Rend le plan technique. |
| **Dancer** | dev | Exécute le plan. |
| **Critic** | validateur | Juge le travail et rend un verdict. |
| **Conductor** (`conductor`, `parallel-conductor`) | coordinateur | Enchaîne les rôles, répond à leurs questions et intègre leur travail. Il ne danse pas et ne compose pas. |

- **Rôle** : Dramaturg, Choreographer, Dancer ou Critic. Le Conductor n'est pas un rôle : il les fait jouer.
- **Worker** : l'instance d'agent (un CLI et un modèle) qu'Orca lance pour jouer un rôle.

**La chaîne et ses réglages**

- **Chaîne** : la suite fixe des phases d'une issue, en deux boucles :
  - **Workshop** : le cadrage (Director, Dramaturg, et le Choreographer en conseil, sans plan) ;
  - **Rehearsal** : plan, code et validation (Choreographer, Dancer, Critic), jusqu'à la **Premiere**, le merge sur `main`.
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
- **Issue draft** : l'issue écrite par le Dramaturg dans l'espace specs, que le Conductor publie ; le Choreographer y ajoute le plan.
- **Slice** (`FEAT-NNN.K`) : une part d'une feature trop grosse pour une seule session du Dancer, proposée par le Choreographer seulement si besoin. Chaque slice est une Rehearsal complète (code, validation, preuve verte, merge sur `main`) et couvre des critères entiers, ou un prérequis technique de la suivante.
- **Glossary** (`glossary.md`) : la langue du projet ; chaque terme avec son nom de code et son texte affiché.

**Langues.** Le plugin (skills, modèles, règles, README) est en anglais ; le PRD, `TASKS.md` et les ADR restent en français tant que la méthode bouge. Le code est toujours en anglais. Les specs sont dans la langue `[project] specs_language` (anglais par défaut) ; le texte affiché par le produit reste dans la langue du produit, cité tel quel. La conversation avec le Director se fait dans sa langue.

## 4. La chaîne

**Workshop** (Dramaturg) → **Rehearsal** : plan (Choreographer) → code (Dancer) → validation (Critic) → **Premiere** : merge sur `main`

Elle est toujours la même. Seuls les axes changent la façon dont elle tourne.

En Workshop, le Choreographer peut être consulté, mais il ne rend son plan officiel qu'en Rehearsal.

## 5. Les rôles

### 5.1 Le contrat, identique pour tous

**Un rôle reçoit :**
- un espace de travail (`main` ou une branche, il ne sait pas lequel et ça lui est égal) ;
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

**Un rôle ne pousse jamais.** Le Dancer commite ; l'intégration (push, train de merge, attente du tampon du Director) est de la plomberie, donc le travail du Conductor.

### 5.2 Les quatre rôles

- **Dramaturg** : cadre le périmètre fonctionnel et rédige l'issue et les specs (dans des fichiers, jamais sur GitHub directement). Répond aux questions de produit. Écrit dans l'espace specs du projet, nulle part ailleurs. Il travaille en amont du Conductor (Workshop interactif) ou lancé par lui (Workshop auto ou discovery).
- **Choreographer** : lit le code, fixe les choix techniques et rend le plan, une section par repo. Seul à écrire les ADR (dossier `[project] adr`) et les spikes (branches `spike/NN-slug`, jamais mergées). Pour le reste, lecture seule : c'est le Conductor qui écrit le plan dans l'issue.
- **Dancer** : exécute sa section du plan en red → green → refactor, commite. Preuve : la commande de preuve de son repo est verte. Écrit dans le code de son repo.
- **Critic** : relit le travail et rend un verdict. Lecture seule. Première ligne de sa réponse : `VERDICT: APPROVED`, `VERDICT: REJECTED` ou `VERDICT: ESCALATE`, puis les preuves et les points à corriger.

Chaque spec de rôle est autonome : la cible, le changement, ce que le rôle peut éditer, la preuve attendue, et si un code de sortie non nul signifie un échec.

### 5.3 Garde-fous : chacun reste dans son périmètre

Une consigne ne suffit pas : un agent peut la lire et la transgresser quand même. Le périmètre est donc tenu par trois couches, de la plus souple à la plus dure. **La dernière est une politique déterministe**, appliquée sans jugement de modèle et identique pour tous les CLI.

**Le périmètre est fixé par rôle, dans Ballet, jamais par tâche :**
- **Dancer** : écrit dans le code de son repo, hors espace specs et hors zones interdites. Le plan ne restreint pas les fichiers qu'il touche ;
- **Dramaturg** : écrit dans l'**espace specs** (brouillons d'issues, specs, glossaire, opportunités…), déclaré dans le profil projet : un repo de specs, ou un dossier dans un repo unique. Jamais dans le code ;
- **Choreographer** : écrit seulement les ADR (dossier `[project] adr`, sur `main`) et les spikes (code jetable et compte rendu `spikes/NN-slug.md`, sur une branche `spike/NN-slug` jamais mergée). Il **rend** son plan ; c'est le Conductor qui l'écrit dans l'issue ;
- **Critic** : lecture seule. Il **rend** son verdict ; c'est le Conductor qui l'écrit dans l'issue ;
- **Conductor** : ne touche pas au code ; il publie sur GitHub ce que les rôles lui rendent, et il intègre, toujours par le script GitHub (section 5.4).

**Zones interdites à tous les rôles**, sauf tâche explicitement dédiée et validée par le Director :
- le harnais : `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/`, `.ballet/`, la configuration des CLI, Ballet lui-même ;
- les ADR, sauf pour le Choreographer ;
- les zones sensibles déclarées dans le profil projet (contrat d'API, sécurité…) ;
- les fichiers de CI et les hooks git ;
- l'historique git : pas de réécriture, pas de force push, pas de suppression de branche.

**Couche 1 — la consigne.** La spec de rôle dit le périmètre et les zones interdites. Un Dancer qui a besoin d'une zone interdite **ne la touche pas** : il le signale au Conductor.

**Couche 2 — les permissions du CLI, quand il en a.** Le worker est lancé avec les droits les plus étroits que son CLI sait imposer :
- Critic en lecture seule (mode plan ou agent en lecture seule) ; comme il n'écrit rien, pas même l'issue, ce mode lui suffit ;
- Choreographer limité aux ADR et à ses branches de spike ;
- Dramaturg limité à l'espace specs ;
- Dancer limité à son repo, sans accès en dehors du dossier de travail.

Ces réglages dépendent de chaque CLI (Claude Code : permissions ; Mistral Vibe : agents personnalisés avec outils et permissions, `outside_workdir = "deny"` ; Grok : à étudier). Ce ne sont pas des hooks, mais leur portée réelle est à vérifier CLI par CLI. Ballet ne compte pas dessus seul.

**Couche 3 — la politique, déterministe.** C'est la couche qui fait foi.
- C'est **un script de Ballet, pas un modèle** : il prend le rôle, l'état du repo avant et après, les zones interdites (défauts de Ballet et profil projet), et rend un code de sortie et la liste des violations.
- Le Conductor l'exécute après chaque rôle et **applique son résultat tel quel** : il ne l'interprète pas, ne le discute pas, ne passe pas outre.
- Ce qu'il vérifie :
  - **Critic** : `HEAD` n'a pas bougé et l'arbre de travail est propre (`git status --porcelain` vide) ;
  - **Choreographer** : sur `main`, tous les fichiers modifiés sont dans le dossier des ADR ; seules des branches `spike/*` ont été créées ; il est revenu sur `main` ; l'arbre de travail est propre ; pas de réécriture d'historique ;
  - **Dramaturg** : tous les fichiers modifiés sont dans l'espace specs, aucun dans une zone interdite ; l'arbre de travail est propre ; pas de réécriture d'historique ;
  - **Dancer** : aucun fichier modifié par ses commits n'est dans l'espace specs, dans le dossier des ADR ni dans une zone interdite ; l'arbre de travail est propre ; le nouveau `HEAD` descend de l'ancien (pas de réécriture d'historique) ; aucune branche ni aucun tag créé ou supprimé.
  - **tous les rôles** : l'état GitHub de l'issue (corps, libellés, commentaires, état) est identique avant et après leur passage.
- Les zones interdites sont des motifs de chemins (globs), pour que la vérification reste mécanique.

**Une violation n'est jamais intégrée.** Le Conductor ne pousse pas ; il renvoie le travail au rôle avec la liste des violations, une fois. À la deuxième violation, il escalade vers le Director. Toute violation est journalisée.

### 5.4 GitHub : un seul point de passage

**Toute interaction avec GitHub passe par le Conductor, au moyen d'un script déterministe de Ballet.** Aucun rôle n'appelle `gh`, l'API GitHub ou `git push`.

- **Le script expose une liste fermée d'opérations**, chacune avec ses entrées vérifiées :
  - lire une issue ;
  - créer ou mettre à jour une issue à partir d'un brouillon de l'espace specs ;
  - écrire le plan rendu par le Choreographer dans sa section de l'issue ;
  - cocher une tâche du plan ;
  - commenter (verdict du Critic, escalade, rapport final) ;
  - poser ou retirer un libellé ;
  - pousser sur `main` (la Premiere) après une politique verte et le tampon de la phase ;
  - fermer l'issue.
- **Aucune opération libre** : pas de commande `gh` arbitraire, pas de suppression, pas de modification des réglages du repo.
- **Le Conductor décide quand appeler une opération, jamais comment elle s'exécute.**
- **Chaque appel est journalisé** (opération, entrées, résultat), comme les transitions.
- **Les rôles produisent, le script publie :** le Dramaturg rédige un brouillon d'issue dans l'espace specs, le Choreographer rend son plan, le Critic rend son verdict ; le Conductor les publie.
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
- **séquentielle** : une issue à la fois, un worker à la fois par repo, sur `main` ;
- **parallèle** : plusieurs issues, un worktree par worker, train de merge.

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
- il dépasse une taille de diff fixée ;
- il modifie ou supprime un test existant au lieu d'en ajouter.

**Côté exécution**
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
  - `conductor` : séquentiel, sur `main`, sans branche ;
  - `parallel-conductor` : un worktree par worker, une file de merge un par un, la gestion des conflits de rebase avec retour à la session du worker, le suivi des ping-pong.
- **Le plan et la validation** sont ses points d'arrêt : il continue seul (auto, sauf escalade) ou il attend le Director (manuel).
- **Le Workshop dit d'où il part** :
  - interactif : le Workshop se fait avant lui, il démarre sur une issue prête ;
  - auto : il lance d'abord un Dramaturg qui cadre la demande ;
  - discovery : il lance d'abord un Dramaturg qui choisit quoi faire.
- Les deux skills font jouer **les mêmes rôles**.
- Le Conductor ne code pas et n'écrit pas de plan : il lance, répond, juge les preuves et intègre.
- Un plafond d'allers-retours Dancer ↔ Critic (2 par défaut) existe dès le séquentiel.
- Rien de destructeur ni de sortant hors du repo sans l'accord du Director.

### 7.1 Le répertoire

- `hybrid-track` = Workshop interactif · plan auto · validation auto · séquentielle
- `auto-track` = Workshop auto · plan auto · validation auto · séquentielle
- `auto-track-discovery` = Workshop discovery · plan manuel · validation manuelle · séquentielle (pour commencer)
- `hybrid-parallel` = Workshop interactif · plan auto · validation auto · parallèle

Une Piece n'est pas un skill de plus : c'est un raccourci qui appelle le bon skill du Conductor avec ses paramètres. Toute autre combinaison reste possible sans rien écrire.

**Piece v0 : `hybrid-track`.** Le Director cadre avec le Dramaturg (Workshop interactif), puis **déclenche en personne le Conductor** (`/ballet:hybrid-track`) : ce geste est son tampon de Workshop, rien ne part automatiquement à la fin du Workshop. Ensuite la Rehearsal (plan, code, validation) s'enchaîne en **auto** jusqu'à la Premiere, sauf escalade. Le Conductor merge dès que le Critic rend `APPROVED` et que la politique est verte.

On part en auto dès le début, pour mesurer la qualité du Critic grâce au journal (refus, allers-retours, builds rouges, merges à corriger après coup). Les garde-fous restent actifs : déclencheurs d'escalade, plafond d'allers-retours, politique déterministe. Des Pieces avec **tampon manuel** (plan, validation) viendront plus tard, au fil des besoins.

## 8. La communication entre workers

- **En étoile** : tout passe par le Conductor. Les workers ne se parlent pas entre eux. Le Conductor sait qui a demandé quoi, peut répondre lui-même, arbitre et trace.
- **Primitives Orca** : un worker pose une question avec `ask` et termine avec `worker_done` ; le Conductor répond avec `reply` et écrit à un worker avec `send`.
- **Types de messages** : question, blocage, proposition de changement de plan, fini.
- **Qui répond** : produit → Dramaturg, technique → Choreographer, hors cadre → Director.
- **Un plafond d'échanges** par tâche avant escalade.
- **Un plan modifié retourne toujours dans l'issue**, jamais seulement dans les messages.
- En parallèle, un Dancer qui découvre une collision avec un autre Dancer le signale au Conductor, qui gère l'ordre de merge.
- Le Dramaturg consulté pendant la Rehearsal est **éphémère par défaut** : lancé à la demande avec l'issue et la question, il répond à partir de l'issue et des specs. Si sa réponse change le périmètre, il met l'issue ou les specs à jour.

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

**Une règle du projet l'emporte sur une règle commune** (un projet client qui impose des PR plutôt que le trunk-based, par exemple).

### 10.5 Le profil projet : `.ballet/config.toml`

Il vit dans le **home du projet** (repo unique, ou repo de specs en multi-repos). C'est un fichier TOML, pas une section de `AGENTS.md` : des scripts déterministes le lisent (politique, GitHub), et les rôles n'y ont pas accès en écriture. Il absorbe les structures différentes : un seul repo (code et specs ensemble) ou un repo de specs avec plusieurs repos de code. Il contient :
- l'**espace specs** où écrit le Dramaturg (repo ou dossier), et où vivent les issues et les plans ;
- les repos, chacun nommé librement par le projet, avec son chemin, sa commande de preuve et ses dépendances (`needs`) : un repo peut en attendre d'autres (par exemple une passerelle qui consomme un contrat généré par un service) ;
- la politique de merge (trunk-based ou PR) ;
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
merge = "trunk"                        # ou "pr"
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

[policy]
sensitive_zones = ["**/contract/**"]   # globs, valables dans tous les repos

[escalation]
max_diff_lines = 400

[roles.dancer]                            # surcharge : le reste hérite des défauts
cli = "mistral-vibe"
```

En mono-repo, une seule entrée `[repos.<nom>]` avec `path = "."` et sans `needs`.

## 11. Lancer Ballet

**Tout part du home du projet** (son repo unique ou son repo de specs), dans un workspace Orca :

1. `/ballet:dramaturg` : le Director cadre avec le Dramaturg (Workshop), qui rédige le brouillon d'issue dans l'espace specs.
2. `/ballet:hybrid-track <brouillon>` : la Piece appelle `conductor` ; le Conductor publie d'abord l'issue sur GitHub par le script (#12), puis enchaîne la Rehearsal. Une issue déjà publiée se lance aussi : `/ballet:hybrid-track #12`.
3. Le Conductor lit le profil et lance Choreographer, Dancer et Critic dans les bons repos (`orca orchestration worker-start --worktree path:<repo>`).

Autres entrées :
- `/ballet:auto-track "<besoin, bug ou retour>"` : le Dramaturg cadre seul, la Rehearsal suit ;
- le Workshop discovery : à déclencher à heure fixe (automations Orca, à étudier).

Pourquoi le home du projet : le Dramaturg et le Conductor y voient le contexte sans effort, Mistral Vibe n'y charge `AGENTS.md` et les skills que dans un dossier de confiance, et une session y correspond à un projet.

## 12. Le monitoring

- **Dès la V1**, le Conductor écrit un événement par transition (JSON lines) : run, issue, phase, rôle, CLI et modèle, début, fin, résultat, allers-retours, escalades et leur motif.
- **Plus tard**, un tableau de bord par-dessus ces données, à la manière de ce qui était prévu pour Nightshift. Sources complémentaires côté Orca : `orca search` dans les sessions, `worker-list`, `inbox`, hooks de statut des agents.
- Il sert à piloter, à **comparer les modèles par rôle**, et à décider quand passer une phase de manuel à auto.

## 13. Contraintes et limites connues

- **Orca tourne en local** : Mac allumé et Orca ouvert, sinon rien n'avance. Les serveurs appariés d'Orca (`--on <environment>`) sont à étudier.
- **Trunk-based et parallèle** : git interdit `main` dans deux worktrees, donc le parallèle sur un même repo passe par des branches courtes, intégrées une par une par le Conductor. Le parallèle entre repos différents n'a pas ce problème.
- **Deux workers ne tournent jamais en même temps sur le même worktree.**
- **Workshop discovery** : c'est le mode le plus risqué ; il commence en mode propositions (issues que le Director valide) avant d'enchaîner seul, et seulement pour certains types de travail.

## 14. Hors périmètre de la V1

- `parallel-conductor` et le train de merge ;
- le Workshop discovery autonome ;
- le tableau de bord de monitoring (le journal, lui, est dans la V1) ;
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
- La source de vérité d'une issue : le brouillon dans l'espace specs, ou l'issue GitHub une fois publiée ? Et comment une modification faite d'un côté rejoint l'autre.
- Comment priver un worker de `gh` et du jeton GitHub quand Orca le lance (variables d'environnement, permissions du CLI).
