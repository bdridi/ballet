# Ballet — PRD

> Méthode commune à tous mes projets pour faire travailler des agents de code (Claude, Grok, Mistral…) en chaîne, sur la plomberie d'Orca.
> Statut : cadrage, rien n'est construit. Version du 11 novembre 2026.

## 1. Pourquoi

- Je veux **une seule méthode** pour tous mes projets, Flownest compris, au lieu de skills recopiés et adaptés projet par projet.
- Je veux **déléguer une issue de bout en bout** à des agents (cadrage, plan, code, validation), avec plus ou moins d'autonomie selon le cas.
- Nightshift (usine sur GitHub Actions) est trop limité en calcul et la coordination y est trop lourde à gérer. Orca fournit déjà la plomberie : lancer des agents, les superviser, faire circuler leurs messages.
- La méthode est d'abord éprouvée sur un **projet de test**, puis étendue à tous les projets.

## 2. Principes

- **Simple is complex enough** : la méthode ajoute le moins de mécanique possible.
- **Les rôles ne connaissent pas la plomberie.** Un rôle reçoit un travail et rend un résultat ; il ignore le flux, les autres agents, le parallélisme, et qui tamponne après lui.
- **Les axes règlent la plomberie, jamais les rôles.** Changer de flux ne touche à aucun rôle.
- **Un harnais commun, hérité sans duplication.** Les règles vivent une fois, dans Ballet ; un projet n'ajoute que ce qui lui est propre.
- **L'auto peut toujours escalader vers moi**, sur des déclencheurs écrits.
- **Tout est tracé** dès la première version, pour pouvoir mesurer avant de lâcher la main.

## 3. Vocabulaire

- **Rôle** : un agent spécialisé. Chacun a son équivalent ballet :
  - **PM** = *Dramaturg* : l'argument, le périmètre fonctionnel ;
  - **Architecte** = *Choreographer* : la partition, le plan technique ;
  - **Dev** = *Dancer* : il exécute ;
  - **Validateur** = *Critic* : il juge et rend un verdict.
- **Director** : moi. Je tamponne et je reçois les escalades.
- **Coordinateur** = *Conductor* : il enchaîne les rôles, répond à leurs questions et intègre leur travail. Il ne danse pas et ne compose pas.
- **Chaîne** : la suite fixe des phases d'une issue, en deux boucles :
  - **Workshop** : le cadrage (moi, le PM, l'architecte en conseil sans plan) ;
  - **Rehearsal** : l'exécution (plan de l'architecte, dev, validateur), jusqu'à la **Premiere**, le merge sur `main`.
- **Axes** (*Parameters*) : les réglages de la chaîne (qui cadre, qui tamponne, comment ça tourne).
- **Préréglage** (*Piece*) : une combinaison nommée des axes, lancée par une commande. Le répertoire est la liste des Pieces.
- **Profil projet** : la description d'un projet que Ballet lit au lieu de la deviner.
- **Tampon** : la validation d'une phase, par un agent (auto) ou par moi (manuel).
- **Escalade** : un agent qui s'arrête et me demande de décider.

Le thème du ballet reste dans la doc ; les noms de skills restent explicites.

## 4. La chaîne

**Cadrage (PM) → Plan (architecte) → Code (dev) → Validation (validateur) → Merge sur `main`**

Elle est toujours la même. Seuls les axes changent la façon dont elle tourne.

Le cadrage est le **Workshop**. Le plan, le code et la validation forment la **Rehearsal**. Le merge est la **Premiere**. En Workshop, l'architecte peut être consulté, mais il ne rend son plan officiel qu'en Rehearsal.

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
- si un humain tamponne après lui ;
- si d'autres agents tournent en parallèle ;
- quel modèle tient les autres rôles ;
- qui répond à ses questions (le coordinateur, le PM ou moi).

**Un rôle ne pousse jamais.** Le dev commite ; l'intégration (push, train de merge, attente de mon tampon) est de la plomberie, donc le travail du coordinateur.

### 5.2 Les quatre rôles

- **PM** : cadre le périmètre fonctionnel et rédige l'issue et les specs (dans des fichiers, jamais sur GitHub directement). Répond aux questions de produit. Écrit dans l'espace specs du projet, nulle part ailleurs. Il travaille en amont du coordinateur (cadrage interactif) ou lancé par lui (cadrage auto ou discovery).
- **Architecte** : lit le code et rend le plan technique, une section par repo. Lecture seule sur le repo : c'est le coordinateur qui écrit le plan dans l'issue.
- **Dev** : exécute sa section du plan en red → green → refactor, commite. Preuve : la commande de preuve du projet est verte. Écrit dans le code de son repo.
- **Validateur** : relit le travail et rend un verdict. Lecture seule. Première ligne de sa réponse : `VERDICT: APPROVED`, `VERDICT: REJECTED` ou `VERDICT: ESCALATE`, puis les preuves et les points à corriger.

Chaque spec de rôle est autonome : la cible, le changement, ce que le rôle peut éditer, la preuve attendue, et si un code de sortie non nul signifie un échec.

### 5.3 Garde-fous : chacun reste dans son périmètre

Une consigne ne suffit pas : un agent peut la lire et la transgresser quand même. Le périmètre est donc tenu par trois couches, de la plus souple à la plus dure. **La dernière est une politique déterministe**, appliquée sans jugement de modèle et identique pour tous les CLI.

**Le périmètre est fixé par rôle, dans Ballet, jamais par tâche :**
- **dev** : écrit dans le code de son repo, hors espace specs et hors zones interdites. Le plan ne restreint pas les fichiers qu'il touche ;
- **PM** : écrit dans l'**espace specs** (brouillons d'issues, specs, glossaire, opportunités…), déclaré dans le profil projet : un repo de specs, ou un dossier dans un repo unique. Jamais dans le code ;
- **architecte, validateur** : lecture seule. Ils **rendent** leur production (plan, verdict) ; c'est le coordinateur qui l'écrit dans l'issue ;
- **coordinateur** : ne touche pas au code ; il publie sur GitHub ce que les rôles lui rendent, et il intègre, toujours par le script GitHub (section 5.4).

**Zones interdites à tous les rôles**, sauf tâche explicitement dédiée et validée par moi :
- le harnais : `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.agents/`, la configuration des CLI, Ballet lui-même ;
- les zones sensibles déclarées dans le profil projet (contrat d'API, sécurité, décisions d'architecture…) ;
- les fichiers de CI et les hooks git ;
- l'historique git : pas de réécriture, pas de force push, pas de suppression de branche.

**Couche 1 — la consigne.** La spec de rôle dit le périmètre et les zones interdites. Un dev qui a besoin d'une zone interdite **ne la touche pas** : il le signale au coordinateur.

**Couche 2 — les permissions du CLI, quand il en a.** Le rôle est lancé avec les droits les plus étroits que son CLI sait imposer :
- architecte et validateur en lecture seule (mode plan ou agent en lecture seule) ; comme ils n'écrivent rien, pas même l'issue, ce mode leur suffit ;
- PM limité à l'espace specs ;
- dev limité à son repo, sans accès en dehors du dossier de travail.

Ces réglages dépendent de chaque CLI (Claude Code : permissions ; Mistral Vibe : agents personnalisés avec outils et permissions, `outside_workdir = "deny"` ; Grok : à étudier). Ce ne sont pas des hooks, mais leur portée réelle est à vérifier CLI par CLI. Ballet ne compte pas dessus seules.

**Couche 3 — la politique, déterministe.** C'est la couche qui fait foi.
- C'est **un script de Ballet, pas un modèle** : il prend le rôle, l'état du repo avant et après, les zones interdites (défauts de Ballet et profil projet), et rend un code de sortie et la liste des violations.
- Le coordinateur l'exécute après chaque rôle et **applique son résultat tel quel** : il ne l'interprète pas, ne le discute pas, ne passe pas outre.
- Ce qu'il vérifie :
  - **rôles en lecture seule** (architecte, validateur) : `HEAD` n'a pas bougé et l'arbre de travail est propre (`git status --porcelain` vide) ;
  - **PM** : tous les fichiers modifiés sont dans l'espace specs, aucun dans une zone interdite ; l'arbre de travail est propre ; pas de réécriture d'historique ;
  - **dev** : aucun fichier modifié par ses commits n'est dans l'espace specs ni dans une zone interdite ; l'arbre de travail est propre ; le nouveau `HEAD` descend de l'ancien (pas de réécriture d'historique) ; aucune branche ni aucun tag créé ou supprimé.
  - **tous les rôles** : l'état GitHub de l'issue (corps, libellés, commentaires, état) est identique avant et après leur passage.
- Les zones interdites sont des motifs de chemins (globs), pour que la vérification reste mécanique.

**Une violation n'est jamais intégrée.** Le coordinateur ne pousse pas ; il renvoie le travail au rôle avec la liste des violations, une fois. À la deuxième violation, il escalade. Toute violation est journalisée.

### 5.4 GitHub : un seul point de passage

**Toute interaction avec GitHub passe par le coordinateur, au moyen d'un script déterministe de Ballet.** Aucun rôle n'appelle `gh`, l'API GitHub ou `git push`.

- **Le script expose une liste fermée d'opérations**, chacune avec ses entrées vérifiées :
  - lire une issue ;
  - créer ou mettre à jour une issue à partir d'un brouillon de l'espace specs ;
  - écrire le plan rendu par l'architecte dans sa section de l'issue ;
  - cocher une tâche du plan ;
  - commenter (verdict du validateur, escalade, rapport final) ;
  - poser ou retirer un libellé ;
  - pousser sur `main` après une politique verte et le tampon de la phase ;
  - fermer l'issue.
- **Aucune opération libre** : pas de commande `gh` arbitraire, pas de suppression, pas de modification des réglages du repo.
- **Le coordinateur décide quand appeler une opération, jamais comment elle s'exécute.**
- **Chaque appel est journalisé** (opération, entrées, résultat), comme les transitions.
- **Les rôles produisent, le script publie :** le PM rédige un brouillon d'issue dans l'espace specs, l'architecte rend son plan, le validateur rend son verdict ; le coordinateur les publie.
- **Garde-fous :** couche 2, les rôles sont lancés sans accès à `gh` ni au jeton GitHub quand le CLI le permet ; couche 3, la politique vérifie que l'état GitHub de l'issue n'a pas bougé pendant le passage d'un rôle.

## 6. Les axes

**Cadrage** — qui décide du périmètre :
- **interactif** : moi et le PM ;
- **auto** : le PM cadre seul une demande, un bug, un retour ou une issue GitHub ;
- **discovery** : le PM choisit seul dans le backlog et les opportunités.

**Plan** — qui tamponne le plan de l'architecte :
- **auto** ;
- **manuel**.

**Validation** — qui tamponne le code avant le merge :
- **auto** : le validateur tamponne ;
- **manuel** : je tamponne, avec le rapport du validateur sous les yeux.

**Exécution** — comment la chaîne tourne :
- **séquentielle** : une issue à la fois, un worker à la fois par repo, sur `main` ;
- **parallèle** : plusieurs issues, un worktree par worker, train de merge.

### 6.1 L'escalade, contrat de l'auto

Toute phase en auto peut escalader vers moi. Les déclencheurs par défaut :

**Côté validateur**
- deux refus de suite (le ping-pong ne converge pas) ;
- un doute sur son propre verdict (`VERDICT: ESCALATE`) ;
- un désaccord persistant avec le dev.

**Côté changement**
- il sort du périmètre fonctionnel de l'issue ;
- un rôle viole la politique une deuxième fois (section 5.3) ;
- il touche une zone sensible déclarée par le projet (contrat d'API, sécurité, décisions d'architecture, harnais…) ;
- il dépasse une taille de diff fixée ;
- il modifie ou supprime un test existant au lieu d'en ajouter.

**Côté exécution**
- un build instable (vert puis rouge sans changement) ;
- en parallèle, un conflit de merge que le dev n'a pas résolu proprement.

La liste est commune ; les seuils et les zones sensibles vont dans le profil projet.

**Ce que fait une escalade :**
- en séquentiel, la chaîne attend mon tampon ;
- en parallèle, seule la tâche escaladée sort du train de merge, les autres continuent ;
- je reçois le verdict, le motif et le diff, de quoi décider sans rouvrir la session ;
- chaque escalade est journalisée avec son motif, pour savoir quels déclencheurs relâcher.

Attendre mon tampon n'est jamais un échec : le coordinateur me prévient et attend.

## 7. Les coordinateurs

- **L'exécution choisit le coordinateur** :
  - `coordinator` : séquentiel, sur `main`, sans branche ;
  - `parallel-coordinator` : un worktree par worker, une file de merge un par un, la gestion des conflits de rebase avec retour à la session du worker, le suivi des ping-pong.
- **Le plan et la validation** sont ses points d'arrêt : il continue seul (auto, sauf escalade) ou il m'attend (manuel).
- **Le cadrage dit d'où il part** :
  - interactif : le cadrage se fait avant lui, il démarre sur une issue prête ;
  - auto : il lance d'abord un PM qui cadre la demande ;
  - discovery : il lance d'abord un PM qui choisit quoi faire.
- Les deux coordinateurs utilisent **les mêmes rôles**.
- Le coordinateur ne code pas et n'écrit pas de plan : il lance, répond, juge les preuves et intègre.
- Un plafond d'allers-retours dev ↔ validateur (2 par défaut) existe dès le séquentiel.
- Rien de destructeur ni de sortant hors du repo sans mon accord.

### 7.1 Les préréglages

- `hybrid-track` = cadrage interactif · plan auto · validation auto · séquentielle
- `auto-track` = cadrage auto · plan auto · validation auto · séquentielle
- `auto-track-discovery` = discovery · plan manuel · validation manuelle · séquentielle (pour commencer)
- `hybrid-parallel` = cadrage interactif · plan auto · validation auto · parallèle

Un préréglage n'est pas un skill de plus : c'est un raccourci qui appelle le bon coordinateur avec ses paramètres. Toute autre combinaison reste possible sans rien écrire.

**Piece v0 : `hybrid-track`.** Je cadre avec le PM (Workshop), puis **je déclenche moi-même le coordinateur** (`/ballet:hybrid-track`) : ce geste est mon tampon de cadrage, rien ne part automatiquement à la fin du Workshop. Ensuite plan, code, validation et merge s'enchaînent en **auto**, sauf escalade. Le Conductor merge dès que le Critic rend `APPROVED` et que la politique est verte.

On part en auto dès le début, pour mesurer la qualité du validateur grâce au journal (refus, allers-retours, builds rouges, merges à corriger après coup). Les garde-fous restent actifs : déclencheurs d'escalade, plafond d'allers-retours, politique déterministe. Des Pieces avec **tampon manuel** (plan, validation) viendront plus tard, au fil des besoins.

## 8. La communication entre agents

- **En étoile** : tout passe par le coordinateur. Les agents ne se parlent pas entre eux. Le coordinateur sait qui a demandé quoi, peut répondre lui-même, arbitre et trace.
- **Primitives Orca** : un worker pose une question avec `ask` et termine avec `worker_done` ; le coordinateur répond avec `reply` et écrit à un worker avec `send`.
- **Types de messages** : question, blocage, proposition de changement de plan, fini.
- **Qui répond** : produit → PM, technique → architecte, hors cadre → moi.
- **Un plafond d'échanges** par tâche avant escalade.
- **Un plan modifié retourne toujours dans l'issue**, jamais seulement dans les messages.
- En parallèle, un dev qui découvre une collision avec un autre dev le signale au coordinateur, qui gère l'ordre de merge.
- Le PM consulté en cours d'exécution est **éphémère par défaut** : lancé à la demande avec l'issue et la question, il répond à partir de l'issue et des specs. Si sa réponse change le cadrage, il met l'issue ou les specs à jour.

## 9. Les agents

- Orca sait lancer, entre autres : `claude`, `grok`, `mistral-vibe`, `codex`, `opencode`, `gemini-cli`, `kimi`.
- **Le routage par rôle** est un réglage de Ballet, surchargeable par le profil projet ; il ne vit jamais dans les rôles. Changer de modèle modifie une ligne.
- Intention de départ : architecte Claude, dev Mistral, validateur Grok ou Claude.
- **Seule règle : validateur ≠ dev**, pour que leurs angles morts ne se recouvrent pas.
- Le dev commence sur Claude comme référence ; les mêmes issues sont ensuite rejouées avec Mistral et comparées (refus du validateur, allers-retours, builds rouges).

## 10. Le harnais commun

### 10.1 Ballet est un plugin

- Le repo `ballet` est **la source** d'un plugin Claude Code, installé une fois au niveau utilisateur. On modifie la méthode dans son repo, on la versionne, chaque projet récupère la mise à jour.
- Les skills s'appellent `/ballet:<skill>` : `/ballet:pm`, `/ballet:hybrid-track #12`, `/ballet:init-project`.

**Le repo Ballet contient :**
- les règles communes : tdd, ddd, bdd, clean code, trunk-based… ;
- les skills de rôles : `pm`, `architect`, `dev`, `validator` ;
- les coordinateurs : `coordinator`, puis `parallel-coordinator` ;
- les préréglages ;
- les réglages par défaut : routage des agents, déclencheurs d'escalade, plafonds ;
- le modèle de profil projet et le skill d'amorçage `init-project` ;
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
- **pas de hooks dans Ballet** : tout garde-fou passe par le coordinateur ou par la preuve. Les permissions propres à chaque CLI ne sont qu'une couche en plus (section 5.3).

### 10.3 Découvert n'est pas appliqué

Un skill est chargé à la demande, selon sa description : rien ne garantit qu'un agent pense à charger `tdd` avant de coder. Les règles sont rendues obligatoires à trois endroits :
- chaque skill de rôle dit quelles règles charger ;
- le profil projet dit quelles règles communes s'appliquent ;
- le coordinateur les nomme dans la spec du worker.

### 10.4 Ce qui reste dans chaque projet

- `AGENTS.md` : les règles propres au domaine ;
- `CLAUDE.md`, qui importe `AGENTS.md` ;
- les skills propres au projet dans `.claude/skills/`, avec `.agents/skills` lié vers ce dossier pour Mistral Vibe (créé par `init-project`) ;
- le profil projet ;
- les issues et les plans.

**Une règle du projet l'emporte sur une règle commune** (un projet client qui impose des PR plutôt que le trunk-based, par exemple).

### 10.5 Le profil projet

Il absorbe les structures différentes : un seul repo (front, back et specs ensemble) ou un repo de specs avec des repos séparés. Il contient :
- les repos et leurs chemins ;
- où vivent les issues et les plans, et l'**espace specs** où écrit le PM (repo ou dossier) ;
- la commande de preuve de chaque repo ;
- l'ordre entre repos (par exemple le back avant le front, quand le front consomme un contrat généré par le back) ;
- la politique de merge (trunk-based ou PR) ;
- les règles communes héritées ;
- les zones sensibles et les seuils d'escalade ;
- les surcharges de routage des agents.

## 11. Lancer Ballet

**Tout part du home du projet** (son repo unique ou son repo de specs), dans un workspace Orca :

1. `/ballet:pm` : je cadre avec le PM, qui rédige le brouillon d'issue dans l'espace specs.
2. `/ballet:hybrid-track <brouillon>` : le préréglage appelle `coordinator`, qui publie d'abord l'issue sur GitHub par le script (#12), puis enchaîne. Une issue déjà publiée se lance aussi : `/ballet:hybrid-track #12`.
3. Le coordinateur lit le profil et lance architecte, dev et validateur dans les bons repos (`orca orchestration worker-start --worktree path:<repo>`).

Autres entrées :
- `/ballet:auto-track "<besoin, bug ou retour>"` : le PM cadre seul, la chaîne suit ;
- la discovery : à déclencher à heure fixe (automations Orca, à étudier).

Pourquoi le home du projet : le PM et le coordinateur y voient le contexte sans effort, Mistral Vibe n'y charge `AGENTS.md` et les skills que dans un dossier de confiance, et une session y correspond à un projet.

## 12. Le monitoring

- **Dès la V1**, le coordinateur écrit un événement par transition (JSON lines) : run, issue, phase, rôle, agent et modèle, début, fin, résultat, allers-retours, escalades et leur motif.
- **Plus tard**, un tableau de bord par-dessus ces données, à la manière de ce qui était prévu pour Nightshift. Sources complémentaires côté Orca : `orca search` dans les sessions, `worker-list`, `inbox`, hooks de statut des agents.
- Il sert à piloter, à **comparer les modèles par rôle**, et à décider quand passer une étape de manuel à auto.

## 13. Contraintes et limites connues

- **Orca tourne en local** : Mac allumé et Orca ouvert, sinon rien n'avance. Les serveurs appariés d'Orca (`--on <environment>`) sont à étudier.
- **Trunk-based et parallèle** : git interdit `main` dans deux worktrees, donc le parallèle sur un même repo passe par des branches courtes, intégrées une par une par le coordinateur. Le parallèle entre repos différents n'a pas ce problème.
- **Deux workers ne tournent jamais en même temps sur le même worktree.**
- **Discovery** : c'est le flux le plus risqué ; il commence en mode propositions (issues que je valide) avant d'enchaîner seul, et seulement pour certains types de travail.

## 14. Hors périmètre de la V1

- `parallel-coordinator` et le train de merge ;
- le cadrage discovery autonome ;
- le tableau de bord de monitoring (le journal, lui, est dans la V1) ;
- un cockpit dans le repo Ballet pour piloter plusieurs projets depuis un seul endroit (registre des projets, discovery entre projets) ;
- la migration de Flownest.

## 15. Plan de test

1. Installer Mistral Vibe. Vérifier, CLI par CLI (Claude, Grok, Mistral), qu'un worker Orca reçoit une spec, voit les skills du plugin et sait appeler `ask` et `worker_done`, sur une tâche bidon.
2. Construire Ballet : règles communes, rôles, routage, modèle de profil, `init-project`, manifeste du plugin. Vérifier l'installation dans les trois CLI.
3. `coordinator` séquentiel, cadrage interactif, plan et validation en auto (Piece v0 `hybrid-track`), avec le journal d'événements.
4. Rejouer les mêmes issues avec un dev Claude puis un dev Mistral, et comparer.
5. Cadrage auto (`auto-track`).
6. Un projet multi-repos (specs + front + back), pour éprouver le profil.
7. `parallel-coordinator` (`hybrid-parallel`).
8. Discovery, en propositions d'abord.
9. Migrer Flownest.

À chaque étape, noter ce qui casse avant de passer à la suivante.

## 16. Ce que la migration de Flownest changera

- Les règles génériques de Flownest (tdd, ddd, clean code, trunk-based) montent dans Ballet ; le domaine (glossaire, invariants du moteur) reste dans le projet.
- `/code` pousse aujourd'hui sur `main` après chaque tâche : dans Ballet, le push sort du rôle dev et passe au coordinateur.
- `/feature`, `/plan`, `/code`, `/slice` sont remplacés par les rôles et les préréglages de Ballet.

## 17. Questions ouvertes

- Le projet de test : leMandat ou un projet neuf ; son home ; repo unique ou plusieurs repos.
- Le compte GitHub du repo Ballet, et sa marketplace de plugin (dépôt GitHub ou chemin local pendant le test).
- Les commandes exactes d'installation du plugin dans chaque CLI.
- Claude Code accepte-t-il `/pm` sans le préfixe `ballet:` quand il n'y a pas d'ambiguïté ?
- Mistral Vibe voit-il les skills du plugin quand Orca le lance (dossier de confiance, chemin du plugin) ?
- Le lien `.agents/skills` → `.claude/skills` suffit-il à Mistral Vibe ?
- Un worker Orca peut-il écrire directement à un autre worker ? (La méthode n'en dépend pas : elle passe par le coordinateur.)
- Les automations Orca suffisent-elles pour déclencher la discovery ?
- Utiliser les Tasks Orca (`run-create`, `task-create --deps`) ou enchaîner les `worker-start` à la main : on commence sans.
- Le PM consulté en cours d'exécution reste-t-il éphémère, ou devient-il persistant ?
- Le format exact du journal d'événements.
- Quelles permissions chaque CLI sait réellement imposer à un rôle lancé par Orca (lecture seule, limite au dossier de travail), et comment Orca les lui passe.
- Le langage des scripts de politique et GitHub (shell ou autre), pour qu'ils tournent partout sans dépendance.
- La source de vérité d'une issue : le brouillon dans l'espace specs, ou l'issue GitHub une fois publiée ? Et comment une modification faite d'un côté rejoint l'autre.
- Comment priver un rôle de `gh` et du jeton GitHub quand Orca le lance (variables d'environnement, permissions du CLI).
