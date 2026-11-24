# Ballet — PRD

> Méthode commune à tous mes projets pour faire travailler des agents de code (Claude, Grok, Mistral…) en chaîne, sur la plomberie d'Orca.
> Ce document décrit la méthode, cible comprise. Ce qui est livré : `release.md` ; ce qui reste : `opportunities.md`. Un point de la méthode pas encore livré renvoie à son opportunité (`OPP-NN`).

## 1. Pourquoi

- Je veux **une seule méthode** pour tous mes projets, Flownest compris, au lieu de skills recopiés et adaptés projet par projet.
- Je veux **déléguer une issue de bout en bout** à des agents (cadrage, plan, code, validation), avec plus ou moins d'autonomie selon le cas.
- Nightshift (usine sur GitHub Actions) est trop limité en calcul et la coordination y est trop lourde à gérer. Orca fournit déjà la plomberie : lancer des agents, les superviser, faire circuler leurs messages.
- La méthode est d'abord éprouvée sur un **projet de test**, puis étendue à tous les projets.

## 2. Principes

- **Simple is complex enough** : la méthode ajoute le moins de mécanique possible.
- **Les rôles ne connaissent pas la plomberie.** Un rôle reçoit un travail et rend un résultat ; il ignore la chaîne, les autres agents, le parallélisme, et qui tamponne après lui.
- **Les modes règlent la plomberie, jamais les rôles.** Passer une boucle d'`assisted` à `autopilot` ne touche à aucun rôle.
- **Un harnais commun, hérité sans duplication.** Les règles vivent une fois, dans Ballet ; un projet n'ajoute que ce qui lui est propre.
- **L'automatique peut toujours escalader vers moi**, sur des déclencheurs écrits.
- **Tout est tracé** dès la première version, pour pouvoir mesurer avant de lâcher la main.

## 3. Vocabulaire

Un terme par concept, et un seul nom partout : la doc, les skills, les clés de config et les commandes emploient les termes ballet (`/ballet:dramaturg`, `[roles.dancer]`). L'équivalent fonctionnel (PM, architecte, dev, validateur, coordinateur) n'apparaît que dans la **description** de chaque skill, pour qu'un agent le reconnaisse, et dans la table ci-dessous.

**Les personnages**

| Terme (et skill) | Équivalent fonctionnel | Ce qu'il fait |
|---|---|---|
| **Director** | — | Moi. Je cadre avec le Dramaturg, je valide en `assisted` et je reçois les escalades. |
| **Dramaturg** | PM | Cadre le périmètre fonctionnel, rédige l'issue et les specs. |
| **Choreographer** | architecte | Écrit le plan technique sur l'issue d'une feature prête, et crée ses slices. |
| **Dancer** | dev | Exécute le plan. |
| **Critic** | validateur | Juge le travail et rend un verdict. |
| **Conductor** | coordinateur | Fait tourner une boucle d'un projet : enchaîne les rôles, porte leurs questions et intègre leur travail. Il ne danse pas et ne compose pas. |
| **Maestro** (`/ballet:maestro`) | superviseur | Le point d'entrée unique du Director pour tous ses projets : une session qui attend sa boîte Orca, où les Conductors et le Monitor écrivent, lui rapporte, porte ses réponses et seule lance les Conductors, les ferme quand ils ont fini, les arrête sur le mot du Director (`stop`, le travail gardé) et redémarre sa propre session pour vider son contexte (`restart`, quand le Monitor le dit trop plein ou sur le mot du Director, et seulement quand plus aucun Conductor ne travaille). |

- **Rôle** : Dramaturg, Choreographer, Dancer ou Critic. Le Conductor n'est pas un rôle : il les fait jouer.
- **Worker** : l'instance d'agent (un CLI et un modèle) qu'Orca lance pour jouer un rôle.

**Les boucles et leurs modes**

- **Chaîne** : la suite fixe des phases d'une issue, en deux boucles :
  - **Workshop** : le cadrage (Director, Dramaturg, et le Choreographer pour l'avis technique) ; il sort une feature prête, jamais un plan ;
  - **Rehearsal** : plan sur le vrai `main`, code et validation (Choreographer, Dancer, Critic), jusqu'à la **Premiere**, le merge de sa PR sur `main`.
- **Mode** : la façon dont une boucle tourne, choisie à son lancement :
  - **`assisted`** (par défaut) : le Director est dans la boucle ; il cadre, valide le plan et reçoit les escalades ;
  - **`autopilot`** : la boucle tourne sans lui ; chaque rôle décide dans son périmètre et trace sa décision. La Rehearsal en autopilot, c'est le mode nuit.
- **File** : les issues GitHub du projet qui attendent leur Rehearsal : type `Task`, `Bug` ou `Feature`, champ Ballet status à `ready`, dans l'ordre du champ Priority puis de l'ancienneté ; les `Slice` suivent leur feature. C'est GitHub qui la tient, par les types et les champs natifs des issues, pas un fichier local.
- **Monitor** : un script déterministe, pas un agent (`ballet_monitor.py`), qui surveille la file sur GitHub et les terminaux des Conductors, et écrit dans la boîte de Maestro l'élément passé prêt, le Conductor disparu, le Conductor fini resté ouvert au-delà de `[conductors] close_finished_after_minutes` (`maestro.toml`, 10 min par défaut), le contexte de la session Maestro quand il passe `[maestro] restart_at_context_percent` de sa fenêtre (30 % par défaut, une fois par session), ou une Rehearsal ou un Workshop sans événement ni commit dans son worktree depuis `[conductors] idle_after_minutes` alors qu'aucun script ni le Director n'a la main (20 min par défaut, deux avis au plus par silence) ; il ne lance, ne ferme ni ne redémarre rien : **il ne poste que des événements, c'est-à-dire des faits (quoi, quand, des chiffres, des liens), jamais une instruction ni une décision** ; les décisions sont celles de Maestro (les lignes `DECISION:` de son script, puis son skill : `launch`, `close`, `restart`, `nudge` : Maestro fait relancer le worker attendu par son Conductor, puis demande au Director) (OPP-01).

**Le reste**

- **Profil projet** : `.ballet/config.toml`, dans le home du projet (repos, preuves, zones sensibles, seuils), que Ballet lit au lieu de la deviner. Le même fichier surcharge les défauts du plugin (routage, seuils).
- **Config et état** : la config est dans des fichiers TOML que le Director édite (`~/.ballet/maestro.toml` pour la machine, le profil de chaque projet) ; l'état vit dans une seule base SQLite pour toute la machine, `~/.ballet/ballet.db` (`ballet_db.py`, OPP-79) : le registre des Conductors, l'état de Maestro (boîte, bail, pause, redémarrage), la file vue par le Monitor, et le journal. Le journal a une seule forme : des **nœuds** (une étape qui commence et finit, jouée par un agent, un script ou le Director) et leurs **événements** (`start`, `end`, ou une marque pendant, dont les échanges entre rôles et entre sessions). La base se met d'elle-même à la version du plugin (migrations numérotées, une copie avant chacune). Les sessions, Rehearsals et Workshops de tous les projets y vivent aussi (`ballet_store.py`) : plus rien n'est écrit dans un projet, leurs fichiers de travail vont dans `~/.ballet/projects/<alias>/`. Les nœuds : le Conductor, la Rehearsal ou le Workshop, le tour de chaque rôle, la preuve, chaque outil de mutation, l'attente du Director. L'état d'avant la base est repris une fois par une commande à part, `ballet_legacy.py import`, qui n'est pas une migration.
- **Tampon** : la validation d'une phase, par un rôle ou par le Director (en `assisted`).
- **Escalade** : le Conductor ou un worker s'arrête et demande au Director de décider.

**L'espace specs** (tenu par le Dramaturg, modèles dans `templates/` du plugin, en anglais)

- **Backlog** (`backlog.md`) : ce qui attend, en quatre sortes d'entrées :
  - **Opportunity** (`OPP-NNN`) : un problème pour quelqu'un, jamais une solution ;
  - **Feedback** : ce qu'un test a montré, en attente d'être classé (gap → bug, rectification → feature révisée, new need → opportunity) ;
  - **Bug** (`BUG-NNN`) : un écart entre la spec et le produit ;
  - **Task** (`TASK-NNN`) : un travail sans comportement visible nouveau.
- **Capability** (`CAP-NNN`) : le chapeau métier de plusieurs features ; le pourquoi, le signal de réussite, les règles métier transverses et les limites, sans critères.
- **Feature** (`FEAT-NNN`) : un comportement visible, quatre critères Gherkin au plus, une issue.
- **Issue** : l'issue GitHub d'une feature prête, d'un bug ou d'une tâche, publiée par le script GitHub à la sortie du Workshop. Elle porte son type natif (`Feature`, `Bug`, `Task`, `Slice`) et trois champs : **Ballet status** (`proposed`, `ready`, `in-rehearsal`, `plan-review`, `escalated`, `done`), **Rehearsal mode** (`assisted`, `autopilot`) et **Plan approval** (`required`, `skipped` ; vide, le profil du projet décide). Types et champs appartiennent au propriétaire du repo (compte ou organisation) et sont créés par `init-project` (`Status` est un nom réservé par GitHub). Le Choreographer y écrit son plan au début de la Rehearsal, et crée les issues de slices. L'issue et son plan ne vivent que sur GitHub, jamais dans l'espace specs.
- **Slice** (`FEAT-NNN.K`) : une part d'une feature trop grosse pour une seule session du Dancer, proposée par le Choreographer seulement si besoin. Chaque slice est une Rehearsal complète (sa branche, code, validation, preuve verte, merge de sa PR sur `main`) et livre au moins un critère entier de bout en bout (slice verticale, jamais une couche : API, puis client, puis écran) ; une slice sans critère n'est admise que pour le walking skeleton d'un repo vide, ou quand le plus petit critère seul dépasse le seuil. Trois slices au plus, découpées par critère (un critère, ou un groupe de critères qui partagent leur code) ; `max_diff_lines` ne fait que marquer une PR trop grosse pour la review, il ne découpe pas.
- **Branche de Rehearsal** (`rehearsal/<ID>`) : la branche courte d'une Rehearsal, dans son propre worktree, créée par le Conductor depuis `main` et supprimée après la Premiere. Le Choreographer et le Dancer y commitent, à tour de rôle ; la PR qui l'intègre porte la validation. Avec des slices, chacune a sa branche, partie de `main` après le merge de la précédente ; les ADR et les règles du plan voyagent avec la première.
- **Branche de Workshop** (`workshop/<ID>`, `<ID>` une ligne du backlog) : la branche courte d'un Workshop en autopilot, dans son propre worktree, où le Dramaturg écrit ses specs ; elles arrivent sur `main` par une PR mergée par le script, puis la branche est supprimée.
- **Glossary** (`glossary.md`) : la langue du projet ; chaque terme avec son nom de code et son texte affiché.

**Langues.** Le plugin (skills, modèles, règles, README, messages des scripts) est en anglais ; le PRD, `opportunities.md`, `release.md` et les ADR restent en français tant que la méthode bouge. Le code est toujours en anglais. Les specs sont dans la langue `[project] specs_language` (anglais par défaut) ; le texte affiché par le produit reste dans la langue du produit, cité tel quel. La conversation avec le Director se fait dans sa langue.

## 4. La chaîne

**Workshop** (Dramaturg) → **Rehearsal** : plan (Choreographer) → code (Dancer) → validation (Critic) → **Premiere** : merge de la PR sur `main`

Elle est toujours la même. Seul le mode de chaque boucle change la façon dont elle tourne.

**Le Choreographer est le pivot** : il joue dans les deux boucles. Au Workshop, il donne son avis technique tôt, parce qu'il peut changer le choix produit, mais il n'y écrit pas de plan. Il planifie au début de la Rehearsal, sur le vrai `main`, juste avant le Dancer : un plan écrit plus tôt se périme pendant que le code bouge. Une issue qui a déjà son plan va droit au Dancer.

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

- **Dramaturg** : cadre le périmètre fonctionnel et rédige les specs (dans des fichiers) ; une feature prête, il publie son issue par le script GitHub, à son type et à son statut (`ready` après le oui du Director, `proposed` en autopilot), sans plan. Répond aux questions de produit. Écrit dans l'espace specs du projet, nulle part ailleurs. Il joue dans le Workshop : avec le Director en `assisted`, seul avec le Choreographer en `autopilot`, où il cadre une demande, un bug ou un retour, ou choisit lui-même dans le backlog.
- **Choreographer** : part d'une feature prête, lit le code, fixe les choix techniques et écrit le plan de l'issue, une section par repo (et crée les issues de slices si besoin), par le script GitHub. Pose ses questions au Dramaturg quand la feature a des manques, et reste éveillé en attendant la réponse. Rend un rapport au Conductor, qui le journalise. Il joue dans les deux boucles (§4). Seul à écrire les ADR (dossier `[project] adr`), les spikes (branches `spike/NN-slug`, jamais mergées) et les règles techniques du projet dans `AGENTS.md`. Pour le reste, lecture seule.
- **Dancer** : exécute sa section du plan en red → green → refactor, commite sur la branche de Rehearsal. Sur un refus, il reprend à partir de la review de la PR, qu'il lit sans y écrire. Preuve : la commande de preuve de son repo est verte. Écrit dans le code de son repo.
- **Critic** : relit le travail dans le worktree et rend un verdict. Lecture seule. Première ligne de sa réponse : `VERDICT: APPROVED`, `VERDICT: REJECTED` ou `VERDICT: ESCALATE`, puis les preuves et **tous** les points bloquants, en un seul lot (jamais remarque par remarque), et des notes optionnelles que le Dancer n'est pas tenu de suivre. Il ne relance ni la preuve ni la mutation : le script a passé la preuve sur le même commit, et lance la mutation en même temps que sa relecture ; verdict et mutation décident ensemble (une mutation rouge renvoie au Dancer même une approbation, puis le Critic relit). Les notes d'une approbation ne retournent pas au Dancer : le script merge et les range dans l'issue de dette technique du projet (une Task `proposed`, libellé `technical-debt`, une section par PR), que le Director joue quand il veut. Le Conductor le publie en une review de la PR. Il ne merge pas : juger et intégrer restent séparés.

Chaque spec de rôle est autonome : la cible, le changement, ce que le rôle peut éditer, la preuve attendue, et si un code de sortie non nul signifie un échec.

### 5.3 Garde-fous : chacun reste dans son périmètre

Une consigne ne suffit pas : un agent peut la lire et la transgresser quand même. Le périmètre est donc tenu par trois couches, de la plus souple à la plus dure. **La dernière est une politique déterministe**, appliquée sans jugement de modèle et identique pour tous les CLI.

**Le périmètre est fixé par rôle, dans Ballet, jamais par tâche :**
- **Dancer** : écrit dans le code de son repo, hors espace specs et hors zones interdites. Le plan ne restreint pas les fichiers qu'il touche ;
- **Dramaturg** : écrit dans l'**espace specs** (backlog, capabilities, features, glossaire…), déclaré dans le profil projet : un repo de specs, ou un dossier dans un repo unique. Jamais dans le code ;
- **Choreographer** : écrit seulement les ADR (dossier `[project] adr`) et `AGENTS.md`, sur la branche de Rehearsal, et les spikes (code jetable et compte rendu `spikes/NN-slug.md`, sur une branche `spike/NN-slug` jamais mergée). `AGENTS.md` lui sert à imposer une règle technique (ses sections projet, jamais le bloc Ballet). Quand il répond à une question du Dancer, il commite dans le même worktree pendant que le Dancer attend : la règle voyage dans la PR avec le code qui la suit. Il écrit le plan de l'issue, et crée les issues de slices, **par le script GitHub uniquement**, puis rend son rapport au Conductor ;
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
- **Quand** : au rapport du Dancer (avant le push), au verdict du Critic (avant sa publication), au plan et à chaque réponse du Choreographer, à la réponse du Dramaturg consulté pendant une Rehearsal.
- Ce qu'il vérifie :
  - **Critic** : `HEAD` n'a pas bougé et l'arbre de travail est propre (`git status --porcelain` vide) ;
  - **Choreographer** : sur la branche de Rehearsal, tous les fichiers modifiés sont dans le dossier des ADR ou sont `AGENTS.md` ; seules des branches `spike/*` ont été créées ; il est revenu sur la branche de Rehearsal ; l'arbre de travail est propre ; pas de réécriture d'historique ;
  - **Dramaturg** : tous les fichiers modifiés sont dans l'espace specs, aucun dans une zone interdite ; l'arbre de travail est propre ; pas de réécriture d'historique (en Workshop assisted, hors Conductor : pas vérifié) ;
  - **Dancer** : il est resté sur la branche de Rehearsal ; aucun fichier modifié par ses commits n'est dans l'espace specs, dans le dossier des ADR ni dans une zone interdite ; l'arbre de travail est propre ; le nouveau `HEAD` descend de l'ancien (pas de réécriture d'historique) ; aucune branche ni aucun tag créé ou supprimé ; aucun test présent sur `main` n'a disparu ni changé de nom (reconnu par son nom : `it`/`test` en JS et TS, `#[test]` en Rust, `def test_` en Python, `Scenario:` en Gherkin). Le corps d'un test existant modifié reste au Critic : au premier run, chaque Rehearsal a retouché les imports d'un fichier de test, une règle à la ligne aurait tout bloqué.
  - **tous les rôles** : l'état GitHub de l'issue et de la PR (corps, libellés, commentaires, reviews, état) est identique avant et après leur passage ; seule exception, le Choreographer, qui crée les slices de son issue (liées à la parente) et écrit leur section `## Plan` (pas encore vérifié).
- **Ses données vivent dans `[policy]`** (défauts du plugin, surchargés par le projet) : un périmètre par rôle, que le projet remplace ou étend sans recopier la méthode, les zones interdites et sensibles, et la façon de reconnaître un test par langage ; le détail des clés est commenté dans le `config.toml` du plugin. Une config qui laisse un rôle écrire `.ballet/config.toml` est refusée.
- Les zones interdites sont des motifs de chemins (globs), pour que la vérification reste mécanique.
- **Un commit appartient au rôle pendant le passage duquel il est apparu** : le Choreographer et le Dancer partagent la branche de Rehearsal, mais jamais en même temps, et l'état avant et après chaque passage suffit à les départager. Les commits du Choreographer et du Dramaturg ne comptent donc pas contre le Dancer (le registre qui le garantit : pas encore fait).

**Une violation n'est jamais intégrée.** Le Conductor ne pousse pas ; il renvoie le travail au rôle avec la liste des violations, une fois. À la deuxième violation, il escalade vers le Director. Toute violation est journalisée.

### 5.4 GitHub : un seul point de passage

**Toute interaction avec GitHub passe par un script déterministe de Ballet** (`scripts/ballet_github.py`). Le Conductor l'appelle ; le Choreographer aussi, pour ses seules opérations (créer l'issue, créer une slice, lire une issue, réécrire son plan) ; le Dancer, seulement pour lire son issue et sa PR. Aucun rôle n'appelle `gh`, l'API GitHub ou `git push` directement.

- **Le script expose une liste fermée d'opérations**, chacune avec ses entrées vérifiées :
  - lire une issue ;
  - publier l'issue d'une feature prête, d'un bug ou d'une tâche, typée et au statut proposée ou prête (à la sortie du Workshop) ;
  - créer une issue de slice, liée à sa parente (Choreographer) ;
  - écrire la section `## Plan` d'une issue (Choreographer) ;
  - cocher une tâche du plan (pas encore fait) ;
  - commenter l'issue (échanges entre rôles, escalade, rapport final) ;
  - poser ou retirer un libellé ;
  - pousser la branche de Rehearsal, ou de Workshop ;
  - ouvrir la PR, liée à l'issue ; ou la PR des specs d'un Workshop, liée à aucune issue (celle de la feature naît après son merge) ;
  - lire une PR et ses reviews (Conductor, Dancer) ;
  - publier une review de la PR (verdict du Critic) et la commenter (rapport du Dancer) ;
  - merger la PR par rebase (la Premiere) après une politique verte, une CI verte et le tampon de la phase, puis supprimer sa branche ; le verdict qui fait foi est le libellé de la PR (`ballet:approved`, `ballet:rejected`, `ballet:escalated`) : le Conductor pose celui du Critic, le Director tranche une escalade en posant le sien, et le merge exige `ballet:approved` posé après le dernier commit ;
  - merger la PR des specs d'un Workshop en autopilot (branche `workshop/<ID>` seule) après une politique verte, sans verdict ni CI : le Workshop n'a pas de Critic, et des specs ne sont pas du code (le projet peut ne pas lancer sa CI sans code source) ;
  - fermer l'issue.
- **Jamais de push direct sur `main`** : `main` ne bouge que par le merge d'une PR.
- **Aucune opération libre** : pas de commande `gh` arbitraire, pas de suppression, pas de modification des réglages du repo.
- **Le Conductor décide quand appeler une opération, jamais comment elle s'exécute.**
- **Chaque appel est journalisé** (opération, entrées, résultat), comme les transitions (pas encore fait).
- **Les rôles produisent, le script publie :** le Choreographer publie lui-même l'issue et ses slices, puis rend son rapport au Conductor, qui le journalise ; le Critic rend son verdict, le Conductor le publie.
- **Garde-fous :** couche 2, les workers sont lancés sans accès à `gh` ni au jeton GitHub quand le CLI le permet ; couche 3, la politique vérifie que l'état GitHub de l'issue n'a pas bougé pendant le passage d'un rôle (pas encore fait).

## 6. Les modes

Chaque boucle se lance en `assisted` (par défaut) ou en `autopilot`.

**Workshop** — il sort une feature prête, jamais un plan :
- **`assisted`** : le Director, le Dramaturg, et le Choreographer pour l'avis technique. La feature sort prête et entre dans la file. C'est une conversation directe avec le Dramaturg (`/ballet:dramaturg`) : ni session de Conductor, ni relais, ni état local.
- **`autopilot`** : le Dramaturg et le Choreographer, sans le Director, dans une **session de Conductor** comme la Rehearsal (personne n'est là pour piloter le Dramaturg). Le Dramaturg cadre une ligne du backlog, ou une demande qui n'y est pas encore (`--request`, la session prend son slug : il la capture d'abord, puis cadre la ligne où elle tombe), ou, sans élément nommé, le Workshop prend la première ligne de *Next up* qui n'a pas encore sa session (toujours **proposée**, quoi que dise le profil). Le Dramaturg consulte le Choreographer avant d'écrire, quand la feature touche un choix technique, par le Conductor comme en Rehearsal, autant de tours que `[escalation] max_exchange_rounds` en permet (le Choreographer ne modifie rien et n'écrit pas de plan ; les échanges sont au journal et commentés sur l'issue dès sa publication) ; ce qu'il tranche seul est écrit dans l'issue, qui porte le libellé **`ballet:decided-alone`**. La feature sort **proposée** : elle n'entre dans la file qu'une fois acceptée par le Director, qui passe le champ `Ballet status` à `ready`. Le portillon est un réglage, **`Queue approval`**, sur le modèle de `Plan approval` : `required` par défaut ; `skipped`, la feature sort `ready` d'emblée. Il se règle dans le profil, par type de travail : `[workshop] queue_approval_skipped = []` (types `Feature`, `Bug`, `Task` ; vide, tout passe par le Director), réservé aux projets et aux types où le Director l'a choisi, en commençant par `Bug` ou `Task` (un bug a la spec pour arbitre, une feature fait deviner du métier : `Feature` est permis, et ce qu'elle a fait deviner reste lisible dans l'issue et sur son libellé `ballet:decided-alone`). Le **full autopilot** est la combinaison : Workshop `autopilot` avec `Queue approval: skipped`, puis Rehearsal `autopilot`, de l'idée à `main` sans humain.
  - La session du Workshop porte une ligne du backlog (`OPP-12`, `FEAT-007`, `BUG-004`, `TASK-009`) ; son état est dans la base (`workshops`), son journal sous un nœud `workshop`. Le Dramaturg travaille dans un worktree sur `workshop/<élément>` ; le script juge son passage (la politique : seul l'espace specs a bougé), ouvre la PR des specs et la merge aussitôt (le Workshop n'a ni Critic ni CI : le oui du Director est la validation, sur l'issue), puis publie l'issue. Personne ne répond à une question dans cette boucle, sauf le Choreographer, consulté par le Conductor (le script le lance en worker dans le même worktree à la première question et lui envoie les suivantes, la politique le juge comme le Critic à chaque réponse, qui revient au Dramaturg ; seul `max_exchange_rounds` borne les tours ; chaque échange est journalisé, puis commenté sur l'issue à sa publication) : le Dramaturg décide dans son périmètre et écrit ce qu'il a décidé (`## Decided alone` de son rapport, recopié dans l'issue, qui porte `ballet:decided-alone`), ou dit qu'il est bloqué (nom de code ou texte affiché non évidents, règle métier qui change d'autres features).

**Rehearsal**
- **`assisted`** : le Director reçoit les escalades, et la file attend sa décision. Le plan attend sa review avant le Dancer : le Director en discute avec le Choreographer par le Conductor (une `question`, un `revise` qui l'amende, puis `approve`), chaque échange publié sur l'issue. Le champ `Plan approval` de l'issue décide, sinon le profil (`[rehearsal] plan_approval`, `true` par défaut) ; à `skipped`, le Choreographer enchaîne.
- **`autopilot`** (le mode nuit) : le Director est hors de la boucle ; le plan part sans validation, et les décisions sont prises par périmètre au lieu de remonter.

**En autopilot, chacun décide dans son périmètre** : le Dramaturg tranche le métier ; le Choreographer l'architecture, et demande le métier au Dramaturg ; le Dancer suit l'architecture, et demande au Choreographer. Le Dramaturg ne sait pas plus que les specs : ce qu'il tranche seul, il le devine. Chaque décision prise sans le Director est donc tracée (ADR pour l'architecture, specs ou rapport pour le métier), **marquée** sur l'issue ou la PR, et réunie dans un **rapport du matin** (OPP-52). Ne remonte au Director en direct que ce qui sort de tous les périmètres, et les déclencheurs mécaniques ci-dessous.

**Un budget borne l'autopilot** (par nuit, par projet ; OPP-53) : atteint, Maestro n'ouvre plus rien et le dit.

**Exécution** : une Rehearsal ouverte à la fois, dans son worktree, une PR à la fois ; plus tard, plusieurs en parallèle, chacune dans son worktree, avec une file de merge (§7).

### 6.1 L'escalade, contrat de l'automatique

Toute phase sans le Director peut escalader vers lui. Les déclencheurs par défaut :

**Côté Critic**
- deux refus de suite (le ping-pong ne converge pas) ;
- un doute sur son propre verdict (`VERDICT: ESCALATE`) ;
- un désaccord persistant avec le Dancer (pas encore détecté).

**Côté changement**
- il sort du périmètre fonctionnel de l'issue ;
- un rôle viole la politique une deuxième fois (section 5.3) ;
- il touche une zone sensible déclarée par le projet (contrat d'API, sécurité, décisions d'architecture, harnais…) ;
- il dépasse une taille de diff fixée, comptée par le script (lignes changées hors `diff_exclude`) et non par le Critic ; hors mode strict, la PR est seulement marquée `ballet:oversized` ; en mode strict, l'escalade précède le Critic, et le Director la lève par `ballet:size-accepted` ;
- il modifie ou supprime un test existant au lieu d'en ajouter.

**Côté exécution**
- la preuve du repo, lancée par le script à chaque rapport du Dancer, reste rouge au-delà du plafond d'allers-retours, ou dépasse `proof_timeout_seconds` ;
- le test de mutation, lancé par le script après la preuve, reste rouge au-delà du plafond d'allers-retours, ou dépasse `[mutation] timeout_seconds` ;
- un build instable (vert puis rouge sans changement, pas encore détecté) ;
- en parallèle, un conflit de merge que le Dancer n'a pas résolu proprement ;
- le budget de l'autopilot est atteint.

La liste est commune ; les seuils et les zones sensibles vont dans `.ballet/config.toml`.

**Ce que fait une escalade :**
- en séquentiel, la chaîne attend le tampon du Director ;
- en parallèle, seule la tâche escaladée sort du train de merge, les autres continuent ;
- le Director reçoit le verdict, le motif et le diff, de quoi décider sans rouvrir la session ;
- chaque escalade est journalisée avec son motif, pour savoir quels déclencheurs relâcher.

Attendre le tampon du Director n'est jamais un échec : le Conductor prévient le Director et attend.

## 7. Le Conductor

- **Une session de Conductor par élément de la file**, neuve : le Monitor signale à Maestro la `task`, le `bug` ou la `feature` passé prêt, et Maestro la lance (seul pour ce que le projet confie à l'auto, sinon sur le oui du Director), puis la suivante après la Premiere. L'état vit dans les scripts et sur GitHub, pas dans la session : rien à garder d'un élément à l'autre, pas de contexte qui dérive.
- **Le Workshop** se lance à la demande du Director (`assisted`), ou à heure fixe (`autopilot`) ; ce qu'il sort entre dans la file par le script GitHub.
- **Plus tard, en parallèle**, le Conductor de Rehearsal ouvre plusieurs Rehearsals, avec une file de merge (`parallel-conductor`, hors V1) :
  - il ne lance en parallèle que des Rehearsals indépendantes : pas de `needs` entre leurs repos, pas de slices d'une même feature ;
  - l'ordre de merge : d'abord les dépendances (`needs`, ordre des slices), puis la première PR prête (verdict, CI, tampon) ;
  - après chaque merge, il rebase les autres branches ouvertes sur `main` ; un conflit retourne au Dancer dans sa session, qui le résout et repasse sa preuve ; le Critic relit la résolution avant le merge ;
  - un conflit mal résolu ou une deuxième résolution ratée : escalade (section 6.1), seule cette Rehearsal sort de la file.
- **Le plan et la validation** sont ses points d'arrêt : il attend le Director en `assisted`, il continue seul en `autopilot`, sauf escalade.
- Le Workshop et la Rehearsal font jouer **les mêmes rôles**.
- Le Conductor ne code pas et n'écrit pas de plan : il lance, répond, juge les preuves et intègre.
- Un plafond d'allers-retours Dancer ↔ Critic (2 par défaut) existe dès le séquentiel.
- **La preuve ne se croit pas sur parole** : à chaque rapport du Dancer, après la politique et avant le push, le script lance lui-même la preuve du repo dans le worktree. Rouge (ou un worktree sali par la preuve), rien n'est poussé, le Critic n'est pas mobilisé : le Dancer reprend avec la fin de la sortie. Au-delà de `max_round_trips` preuves rouges, ou trop longue, escalade.
- **Le test de mutation, après la preuve** : Ballet porte la méthode, le projet l'outil. Le projet fige l'outil, sa config (où s'excluent les équivalents, chacun avec sa raison) et déclare une entrée par outil dans son profil (`[[repos.<repo>.mutation]]`) ; Ballet calcule le diff de la branche contre son ancêtre commun avec `origin/main` (contre le commit de la dernière mutation verte, s'il y en a une), le passe à chaque outil (`{diff}`, `{files}`, `{ranges}`), et le code de sortie décide. Trop long pour un appel du Conductor, il part en arrière-plan, **en même temps que le Critic**, et le réveille par Orca à sa fin ; le verdict et la mutation décident ensemble, le premier arrivé attend l'autre. Rouge, c'est un point bloquant : le Dancer reprend, en un seul tour, avec les points du Critic et les survivants, puis le Critic relit, même s'il avait approuvé ; au-delà de `max_round_trips`, ou d'une heure, escalade. L'outil tourne pendant que le Critic lit le worktree : il ne mute pas les sources en place (cargo-mutants copie l'arbre par défaut), et ce qu'il écrit dans le worktree est ignoré par git. Un survivant se tue par un test unitaire ; le Critic juge chaque exclusion (`ballet:tdd`). `[mutation] enabled = false` coupe le nœud sans retirer les entrées.
- Rien de destructeur ni de sortant hors du repo sans l'accord du Director.

### 7.1 La Rehearsal séquentielle

Maestro joue la file dans son ordre (à trancher, §17). Une seule Rehearsal ouverte à la fois, un seul worker actif. Les dépendances entre éléments sont les liens natifs de GitHub (« Blocked by » / « Blocking ») : ils décident de ce qui peut partir, un élément ne part que si tous ses bloqueurs sont fermés, et le Dramaturg les pose (ligne `Depends on:` des specs, lien créé à la publication de l'issue ; il ne crée une dépendance que si une feature ne peut vraiment pas être construite avant l'autre, faute de quoi le parallélisme se perd). Un bloqueur fermé *not planned*, un cycle ou un bloqueur illisible se tranche par le Director. À la Premiere d'une Rehearsal, Maestro lance la suivante, depuis `main` : une feature est donc planifiée sur le vrai `main`, après la dernière Premiere de la précédente. Une escalade met la file en pause ; le Director tranche, puis la Rehearsal reprend, et la file avec elle.
- **Une feature sans plan** ouvre une Rehearsal de **planification**, dont le seul rôle est le Choreographer : il tranche, découpe et publie sans attendre de oui ; les questions de produit vont au Dramaturg, ce qu'il ne peut pas trancher au Director (escalade). Une issue sans plan suit le même chemin.
- **À son rapport**, le script lit sur GitHub l'issue et ses slices (`Part of #N` en première ligne) et les place en tête de file ; une issue sans slices entre seule.
- **Les ADR** du Choreographer (et `AGENTS.md`) partent avec la première slice, ou l'issue unique : le worktree de la planification devient le sien, ses commits restent au Choreographer pour la politique et arrivent sur `main` au premier merge. Pas de PR d'ADR à part.
- **Le plan** : en `assisted`, la file s'arrête après sa publication, le temps de sa review par le Director (une discussion avec le Choreographer, par le Conductor, jusqu'à `approve`), sauf si l'issue ou le profil la saute ; en `autopilot`, on enchaîne.
- **La Premiere** : le Conductor merge la PR dès que le Critic rend `APPROVED`, que la politique et la CI sont vertes.

On mesure la qualité du Critic grâce au journal (refus, allers-retours, builds rouges, merges à corriger après coup) avant de lâcher la main ; les garde-fous restent actifs dans les deux modes : déclencheurs d'escalade, plafond d'allers-retours, politique déterministe.

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
- Les skills s'appellent `/ballet:<skill>` : `/ballet:dramaturg`, `/ballet:rehearsal #12`, `/ballet:init-project`.

**Le repo Ballet contient :**
- les règles communes : tdd, ddd, bdd, clean code, trunk-based… ;
- les skills de rôles : `dramaturg`, `choreographer`, `dancer`, `critic`, chacun avec son équivalent fonctionnel dans sa description ;
- le skill du Conductor, et une commande par boucle (Workshop, Rehearsal) avec son mode ;
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

[conductor]
model = "sonnet"          # facultatif : le modèle des Conductors de ce projet ; absent, `[conductors] model` de
                          # ~/.ballet/maestro.toml pour toute la machine, sinon haiku (il relaie des scripts)

[escalation]
max_round_trips = 2       # allers-retours Dancer ↔ Critic
```

**Le coût du lancement d'une session.** Chaque session `claude` démarre avec un socle fixe (prompt système, définitions d'outils, serveurs MCP du poste, skills) relu à chaque tour. Les sessions que Ballet lance lui-même, le Conductor (`ballet_launch.py`) et Maestro (`ballet_maestro.py`), partent donc allégées (`ballet_session.py`) : aucun serveur MCP (`--strict-mcp-config` et une config MCP vide), les seuls outils intégrés de leur rôle (`--tools`, dont `Skill` : les skills du plugin Ballet restent chargés), et un cache de prompt d'une heure (`CLAUDE_CODE_PROMPT_CACHE_TTL=1h`, Claude Code ≥ 2.1.242 ; au-delà du quota d'abonnement ou sur une clé d'API le défaut est de 5 minutes, et les attentes de mutation ou du Critic réécrivent tout le contexte). Mesuré sur `claude -p` : 38 100 tokens de socle par défaut, 33 800 sans serveur MCP, 17 600 avec en plus les outils du rôle seuls. Les modèles se règlent sans toucher au harness, qui reste Claude Code : le Conductor prend `[conductor] model` du profil du projet, sinon `[conductors] model` de `~/.ballet/maestro.toml` pour toute la machine, sinon `haiku` ; Maestro prend `[maestro] model` de `~/.ballet/maestro.toml` (`sonnet` par défaut), lu à la création de sa session : un changement s'applique au prochain `/ballet:setup upgrade` (ou `restart`). Les workers sont lancés par `orca orchestration worker-start`, qui ne transmet ni option ni variable à `claude` (seulement `--model` et `--effort`) : leur socle est celui des réglages d'agent d'Orca (`agentDefaultArgs` et `agentDefaultEnv` de `claude`, que le Director pose une fois dans Orca).

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
max_diff_lines = 1500
max_diff_strict = true                   # escalade avant le Critic au-delà du seuil (défaut : false)
ci_wait_seconds = 480                    # la Premiere attend une CI en cours jusque-là (défaut : 480, sous 600)
proof_timeout_seconds = 420              # la preuve lancée par le script au rapport du Dancer (défaut : 420, sous 600)
diff_exclude = ["*.lock", "**/generated/**"]

[mutation]
enabled = true                           # false : le nœud de mutation est sauté, les entrées restent (défaut : true)
timeout_seconds = 3600                   # le budget de tous les outils, en arrière-plan (défaut : 3600)

[roles.dancer]                            # surcharge : le reste hérite des défauts
cli = "mistral-vibe"
```

En mono-repo, une seule entrée `[repos.<nom>]` avec `path = "."` et sans `needs`.

## 11. Lancer Ballet

**Tout part du home du projet** (son repo unique ou son repo de specs), dans un workspace Orca. Chaque boucle a sa commande :

1. le Workshop, `/ballet:workshop` : `assisted` par défaut, le Director cadre en direct avec le Dramaturg (`/ballet:dramaturg`), qui demande l'avis du Choreographer au besoin, sans session ; la feature prête est publiée en issue et entre dans la file. `/ballet:workshop --autopilot [<élément>]` (une ligne du backlog, `BUG-004` ; sans élément, la première de *Next up*) confie l'élément à un Conductor, qui le joue jusqu'à l'issue publiée (`proposed`, ou `ready` selon `[workshop] queue_approval_skipped`, sauf pour l'élément que le Workshop a choisi seul) ;
2. le Monitor surveille la file et signale à Maestro chaque élément prêt ; Maestro lance `/ballet:rehearsal <élément>` dans une session neuve, au mode lu sur son champ Rehearsal mode (`--autopilot`, `--require-plan-approval`) ; le Director peut aussi la lancer lui-même sur une issue (`#12`) ;
3. le Conductor lit le profil et lance Choreographer, Dancer et Critic dans les bons repos (`orca orchestration worker-start --worktree path:<repo>`).

Pourquoi le home du projet : le Dramaturg et le Conductor y voient le contexte sans effort, Mistral Vibe n'y charge `AGENTS.md` et les skills que dans un dossier de confiance, et une session y correspond à un projet.

## 12. Le monitoring

- **Sur GitHub**, la trace des échanges : l'issue (plan, amendements, questions et réponses) et la PR (rapports du Dancer, verdicts du Critic).
- **Dès la V1**, le Conductor écrit un événement par transition (JSON lines) : run, issue, phase, rôle, CLI et modèle, début, fin, résultat, allers-retours, escalades et leur motif (format à figer avec la base : OPP-79).
- **Les frictions et le coût** (`scripts/ballet_frictions.py`, `scripts/ballet_cost.py`) : à la fin de chaque Rehearsal et de chaque Workshop, sans LLM, la ligne `frictions of <ID> (<durée>): …` que le `done` donne à Maestro dit ce qui a coincé, puis ce que la Rehearsal a coûté : `cost ~$8.65 API equivalent (19.7M tokens, 19.1M from cache): Choreographer $5.32, Dancer $1.60, …`. Le coût vient des journaux de Claude Code (`~/.claude/projects/`), dédoublonnés par réponse : les sessions du worktree de la Rehearsal (le rôle se lit dans leur premier message) pendant sa fenêtre de temps, et le Conductor du projet quand une seule session `/ballet:rehearsal <élément>` est active dans cette fenêtre (sinon il est laissé de côté, et la ligne le dit). Le Director est sur un abonnement : le dollar est un équivalent au prix de l'API (table de prix en tête du script), les tokens donnent la mesure du quota. Ne sont pas comptés : les appels annexes de Claude Code (titre de session), et ce que le Conductor dépense hors de la fenêtre d'une Rehearsal. Un journal introuvable ne fait jamais échouer la fin : le coût est dit absent. Il sert à juger les optimisations (reprise du Dancer en `resume`, `compact` ou `fresh`).
- **La Scène** (`scripts/ballet_stage.py`) : une page locale en lecture seule, pour tous les projets de la machine (un sélecteur pour n'en garder qu'un), lue dans la base (nœuds et événements, états, registre des Conductors, file `ready` du Monitor, `runtime`) : un Dashboard (la santé de Ballet, les indicateurs, l'activité, le temps par ticket, la durée des Rehearsals, les diffs face à leur limite, les rôles, les escalades), ce qui est en scène (ce qui attend le Director d'abord), le programme et les issues `proposed`, les Workshops, les Rehearsals par session de Conductor, les tickets et les Premieres ; pour chaque représentation, ses transitions, sa communication et son fil, mis à jour en direct. Elle n'écrit rien : une issue `proposed` s'accepte sur GitHub. C'est un outil d'observation pour se forger des convictions, pas un livrable de la V1 (§14).
- **Plus tard**, un vrai tableau de bord par-dessus ces données, à la manière de ce qui était prévu pour Nightshift. Sources complémentaires côté Orca : `orca search` dans les sessions, `worker-list`, `inbox`, hooks de statut des agents.
- Il sert à piloter, à **comparer les modèles par rôle**, et à décider quand passer une boucle d'`assisted` à `autopilot`.

## 13. Contraintes et limites connues

- **Orca tourne sur la machine du Director ou un VPS** : allumée et Orca ouvert, sinon rien n'avance ; Orca sans écran sur un VPS reste à vérifier. Les serveurs appariés d'Orca (`--on <environment>`) sont à étudier.
- **Branches courtes** : une branche de Rehearsal vit le temps d'une issue ; `main` ne reçoit que des PR validées, mergées une par une par le Conductor.
- **Deux workers ne tournent jamais en même temps sur le même worktree.**
- **Le Workshop en autopilot qui choisit seul dans le backlog** est le plus risqué : il commence en propositions (des features que le Director valide) avant d'enchaîner seul, et seulement pour certains types de travail. Livré en propositions seulement (OPP-70) : l'élément choisi seul sort toujours `proposed`.

## 14. Hors périmètre de la V1

- la Rehearsal en parallèle et la file de merge ;
- Maestro, le point d'entrée du Director pour plusieurs projets : priorités et budget entre eux, résumé du matin (OPP-53, OPP-52) ;
- le Workshop en autopilot qui choisit seul dans le backlog, sans propositions (il choisit déjà, mais ses issues sortent `proposed`) ;
- le tableau de bord de monitoring abouti (le journal est dans la V1 ; la Scène n'en est que le concept, voir §12) ;
- la migration de Flownest.

## 15. Plan de test

La méthode s'éprouve sur un **projet de test** (`../antimurphy`, mono-repo Rust et TS) avant d'être étendue, une marche à la fois, en notant ce qui casse avant de passer à la suivante :

1. la plomberie : chaque CLI reçoit sa spec, voit les skills, sait appeler `ask` et `worker_done` (ADR 0001) ;
2. la Rehearsal séquentielle, avec le journal ;
3. les mêmes issues rejouées avec un Dancer Claude puis Mistral, et comparées ;
4. les deux boucles en `autopilot`, Workshop puis Rehearsal (le mode nuit) ;
5. la file sur GitHub, le Monitor et Maestro ;
6. un projet multi-repos, pour éprouver le profil ;
7. la Rehearsal en parallèle ;
8. la migration de Flownest.

## 16. Ce que la migration de Flownest changera

- Les règles génériques de Flownest (tdd, ddd, clean code, trunk-based) montent dans Ballet ; le domaine (glossaire, invariants du moteur) reste dans le projet.
- `/code` pousse aujourd'hui sur `main` après chaque tâche : dans Ballet, le push sort du Dancer et passe au Conductor.
- `/feature`, `/plan`, `/code`, `/slice` sont remplacés par les rôles et les boucles de Ballet.

## 17. Questions ouvertes

Tranchées : voir `docs/ADR/`.

- La marketplace du plugin au-delà du test (pendant le test : chemin local).
- Un worker Orca peut-il écrire directement à un autre worker ? (La méthode n'en dépend pas : elle passe par le Conductor.)
- Les types et les champs natifs des issues, par l'API : lecture, écriture, et trace de leurs changements dans la timeline (OPP-03, à vérifier par un spike).
- En autopilot, une Rehearsal escaladée : la file attend le Director, ou passe à l'élément suivant qui n'en dépend pas ? Tranché en 0.36.0 : une session par élément, Maestro lance les autres.
- Le Monitor : un script qui tourne en continu dans un terminal Orca (OPP-01, OPP-02) ; reste à trancher comment réveiller le Workshop en autopilot à heure fixe.
- Utiliser les Tasks Orca (`run-create`, `task-create --deps`) ou enchaîner les `worker-start` à la main : on commence sans.
- Le Dramaturg consulté pendant la Rehearsal reste-t-il éphémère, ou devient-il persistant ?
- Le format exact du journal d'événements (OPP-79).
- Quelles permissions chaque CLI sait réellement imposer à un worker lancé par Orca (lecture seule, limite au dossier de travail), et comment Orca les lui passe (Grok : pas vérifié).
- Qui pousse les commits du Dramaturg (specs, sur `main`) quand l'espace specs est dans le repo de code : une PR de specs, ou le Conductor au début de la Rehearsal ?
- Un repo sans CI : la Premiere se contente-t-elle de la preuve locale ?
- Signer les commits par rôle (une clé par rôle) n'a de sens qu'avec une isolation par l'OS (un utilisateur ou un bac à sable par rôle) : sous le même utilisateur, le Dancer peut lire la clé du Choreographer. Même chantier que la ligne suivante.
- Comment priver un worker de `gh` et du jeton GitHub quand Orca le lance (variables d'environnement, permissions du CLI).
