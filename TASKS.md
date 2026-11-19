# Ballet — plan d'implémentation

> Piano piano : on commence par ce qui peut tout remettre en cause (la plomberie Orca et les trois CLI), puis des briques testables seules, et on n'assemble la chaîne qu'à la fin.
> Chaque étape se termine par quelque chose qu'on peut montrer, et par une note sur ce qui a cassé.
> Référence : `PRD.md`. Règles du repo : `AGENTS.md`.

## Étape 0 — Décisions de départ ✅

- [x] Projet de test : `../antimurphy` (mono-repo Rust + TS/pnpm).
- [x] Marketplace du plugin : chemin local pendant le test.
- [x] Scripts : Python, dernière version, bibliothèque standard uniquement, style « histoire » (voir `AGENTS.md`).

## Étape 1 — Spike de plomberie (PRD §15.1) ✅

But : vérifier que la méthode tient sur Orca avant de construire quoi que ce soit. Seule étape qui peut invalider le PRD.
Résultat : `docs/ADR/0001-plomberie-orca-trois-cli.md` (branche `spike/01-plomberie`).

- [x] Installer Mistral Vibe.
- [x] Écrire une tâche bidon et un skill bidon (skill projet ; le plugin local est testé à l'étape 2).
- [x] Pour chaque CLI (Claude, Grok, Mistral Vibe), un worker Orca :
  - [x] reçoit sa spec ;
  - [x] voit le skill (Claude et Vibe nativement ; Grok non, voir l'ADR) ;
  - [x] pose une question avec `ask` et reçoit la réponse ;
  - [x] termine avec `worker_done`.
- [x] Permissions imposables : **reportées** au spike 1 bis (voir ci-dessous). En attendant, consignes dans la spec et vérification du diff par le Conductor.
- [x] Résultats dans `spikes/01-plomberie.md` (sur la branche du spike).

**Fini quand** : on sait, CLI par CLI, ce qui marche, et le PRD est corrigé si besoin.

## Spike 1 bis — Permissions imposées (plus tard)

- [ ] Grok : privation du jeton par l'environnement du lancement (limite d'usage gratuit atteinte au spike 1).
- [ ] Grok : limite au dossier de travail (le bac à sable `--sandbox workspace` n'a rien bloqué sous `/tmp`).

## Étape 2 — Squelette du plugin ✅ (réserve : Grok)

Résultat : `docs/ADR/0002-plugin-unique-trois-cli.md`.

- [x] Manifeste du plugin Ballet, installable depuis le chemin local (`.claude-plugin/plugin.json`, marketplace locale `ballet-local`).
- [x] Un skill `dramaturg` minimal (description : « Dramaturg (PM)… »).
- [x] Les règles communes en skills d'un fichier chacun : `tdd`, `bdd`, `ddd`, `clean-code` (trunk-based viendra avec la politique de merge).
- [x] Installation vérifiée : Claude et Vibe répondent à `/ballet:dramaturg`. Grok : installé et plugin reconnu, appel du skill **non testé** (limite d'usage gratuit).
- [x] `/dramaturg` sans préfixe : accepté par Claude et Vibe.
- [ ] Grok : vérifier `/ballet:dramaturg` quand la limite est levée.

**Fini quand** : un seul plugin sert les trois CLI.

## Étape 3 — La config ✅

Résultat : `docs/ADR/0003-schema-config-et-critic-dancer.md`, `config.toml`, `scripts/ballet_config.py`, `scripts/init_project.py`, `skills/init-project/`, `tests/` (`python3 -m unittest discover -s tests`).

- [x] `config.toml` par défaut du plugin (routage par rôle, plafonds, seuils).
- [x] Schéma de `.ballet/config.toml` (PRD §10.5), et réponse à la question « Critic ≠ Dancer avec surcharges ».
- [x] Script de config : lire, fusionner clé par clé, vérifier (champs projet obligatoires, Critic ≠ Dancer, cycles et repos inconnus dans `needs`).
- [x] Tests du script, sans agent.
- [x] `init-project` minimal qui génère `.ballet/config.toml`, `AGENTS.md`, `CLAUDE.md` et le lien `.agents/skills`.
- [x] Lancer `init-project` sur antimurphy (fichiers créés, non commités ; la preuve y est un marqueur qui échoue).
- [x] README utilisateur (installation par CLI).

**Fini quand** : antimurphy a sa config, et le script refuse les configs invalides.

## Étape 4 — Les rôles, un par un, lancés à la main

Sans Conductor : on ajuste chaque spec de rôle isolément, quand c'est encore facile.

- [ ] `dramaturg` : un vrai Workshop sur antimurphy, jusqu'à une feature prête dans l'espace specs.
  - [x] Modèles de l'espace specs, inspirés de flownest-specs : backlog (opportunités, retours, bugs, tâches), capability, feature, brouillon d'issue, glossaire (`templates/`).
  - [x] Skill `dramaturg` : capturer, trier les retours, arbitrer, grouper, découper, écrire et réviser une feature, rédiger le brouillon d'issue.
  - [x] Workshop réel sur antimurphy (CAP-001 → FEAT-001) : signal de réussite et règles métier dans la capability, règle de langue (0.2.0).
  - [x] Plugin en anglais, specs en anglais par défaut (`[project] specs_language`), texte affiché cité dans la langue du produit (0.3.0).
  - [ ] Ajustements après les Workshops suivants.
  - [ ] Plus tard : parcours, flux et expérience (le `/storyboard` de flownest).
  - [ ] Plus tard : partager les skills user de Claude avec Vibe (lien `~/.vibe/skills` → `~/.claude/skills`), une fois le ménage des skills user fait.
- [ ] `choreographer` : rend un plan, une section par repo, en lecture seule.
  - [x] Skill `choreographer` : interview technique, décisions explicites (le Dancer n'improvise pas), plan par repo, slices seulement si besoin (0.4.0).
  - [x] Seul le Choreographer écrit les ADR (`[project] adr`) et les spikes (branches `spike/NN-slug`, jamais mergées) ; modèles `adr.md` et `spike.md` (0.4.1).
  - [x] Le Choreographer impose les règles techniques dans `AGENTS.md`, sections projet seulement (0.4.2).
  - [x] Premier plan réel de FEAT-001 sur antimurphy : un tour Choreographer → Dramaturg a ajusté la feature et le glossaire.
  - [x] Le Choreographer part de la feature et crée l'issue avec son plan, et ses slices, par le script GitHub (`publish`, `slice`, `read`, `plan`) ; plus de brouillon d'issue chez le Dramaturg ; rapport au Conductor (0.5.0).
  - [x] Format de message unique entre rôles (`templates/message.md`), plafond `[escalation] max_exchange_rounds` ; le Choreographer pose ses questions au Dramaturg et reste éveillé ; réponse simple ou modification commitée des specs, sans diff (0.5.0).
  - [ ] Créer l'issue de FEAT-001 sur anti-murphy par le script, retirer `specs/issues/`.
  - [x] Retours du premier run (#2) : section « Answering the Dancer » (commit sur ses seuls chemins, vérifier une dépendance avant de l'accepter), sonde d'outillage avant un plan qui fixe versions et commandes, spikes sur chaque chemin (dev, test, CI), zones interdites du Dancer dans le plan (action du Director), `### Amendments` dans le plan, `AGENTS.md` dit le quoi sans versions ; `plan` refuse un brouillon complet (0.7.0).
- [ ] `dancer` : exécute le plan en red → green → refactor, commite, preuve verte.
  - [x] Skill `dancer` : sa section du plan, un commit vert par tâche, jamais de push ni de test existant modifié, questions au Choreographer ou au Dramaturg en restant éveillé, rapport au Conductor (0.6.0).
  - [x] Premier run réel sur FEAT-001 d'antimurphy.
    - [x] Slice #2 (walking skeleton) : 7 tâches, preuve verte, 3 questions au Choreographer.
  - [x] Chaque Rehearsal sur sa branche `rehearsal/<ID>`, dans son worktree, intégrée par une PR que le Conductor merge par rebase ; le Critic rend ses remarques en un lot, publiées en une review ; sur un refus, le Dancer relit la PR ; clé `[project] merge` retirée (ADR 0004, 0.7.0).
- [ ] `critic` : rend un verdict (message `type: verdict`, première ligne `VERDICT: …`), en lecture seule.
  - [x] Skill `critic` : relance la preuve, vérifie tâches, critères, décisions, règles et périmètre sur le diff de la branche de Rehearsal ; points bloquants en un seul lot, notes optionnelles ; relecture point par point au round suivant ; `read-pr` dans le script GitHub (0.8.0).
  - [x] Première review réelle : la PR de la slice #2 d'antimurphy, ouverte à la main par le Director ; un refus (une dépendance hors plan), corrigé par le Dancer, puis `APPROVED`.
- [ ] Les règles communes minimales chargées par chaque rôle (tdd, clean code, trunk-based).

**Fini quand** : une feature d'antimurphy passe à la main de l'état prêt au code validé.

## Étape 5 — Les scripts déterministes

- [ ] Script de politique : état git avant et après, zones interdites, périmètre par rôle (dont ADR, `AGENTS.md` et branches `spike/*` réservés au Choreographer), état GitHub de l'issue inchangé.
  - [x] v0 (0.15.0) : `ballet_policy.py`. Pour tous : branche, historique (le `HEAD` d'avant reste un ancêtre), branches et tags (`spike/*` permis au Choreographer), arbre propre (sauf le Choreographer qui répond, l'arbre du Dancer est en cours). Critic : `HEAD` immobile. Choreographer : ADR et `AGENTS.md` seulement. Dancer : le diff net de la branche face à `main` hors specs, ADR, harnais, CI, hooks et `sensitive_zones` (sauf les commits du Choreographer, notés dans l'état), aucun test de `main` disparu ou renommé. Données dans `[policy]` du `config.toml` : un périmètre par rôle (`[policy.roles.<rôle>]` : `writes` et `except` de la méthode, remplaçables ; `extra_writes` et `extra_except` vides, pour étendre sans recopier ; `branches`), `forbidden_zones`, `sensitive_zones`, `test_names` par langage. Aucun rôle ne peut écrire `.ballet/config.toml`, sinon la config est refusée. Le Dramaturg consulté pendant une Rehearsal est vérifié à sa réponse et commite sur la branche de Rehearsal ; ses commits, comme ceux du Choreographer, ne comptent pas contre le Dancer. Testé sur des repos jouets ; rejoué sur les 4 Rehearsals d'antimurphy (#9 à #12) : aucune fausse alerte.
  - [ ] L'état GitHub de l'issue et de la PR inchangé pendant le passage d'un rôle.
  - [ ] Le Dramaturg en Workshop (sur `main`, hors Conductor) : pas encore vérifié.
  - [ ] Les spikes du Choreographer quand il répond au Dancer : un `checkout` dans le worktree partagé, par-dessus le travail en cours du Dancer. Lui donner son propre worktree.
  - [ ] Plus tard : un test existant dont le corps change (une attente affaiblie) ; aujourd'hui le Critic seul le voit.
- [ ] Script GitHub : la liste fermée d'opérations (PRD §5.4), chaque appel journalisé. Déjà là : `read`, `publish`, `plan`, `slice` (0.5.0), `read-pr` (0.8.0), `push`, `open-pr`, `review` (un commentaire par point situé `fichier:ligne` du diff, le reste dans le corps), `verdicts` (un commentaire global de la PR, réécrit à chaque verdict : une ligne par tour), `resolve` (la section `## Fixed` du rapport du Dancer : réponse « Fixed in <sha> » dans le fil, puis résolu), `comment-issue`, `comment-pr`, `merge` (0.9.0 ; `merge` refuse sans dernier verdict `APPROVED` postérieur au dernier commit, et sans CI : une CI absente n'est pas verte), `label` (0.10.0), `close` (0.11.0). Reste : cocher une tâche du plan, journalisation des appels.
- [x] Lecture de l'en-tête JSON des messages (`ballet_message.py`), escalade sur un en-tête invalide, compte des tours par sujet et paire de rôles (0.9.0).
- [ ] Compter les tours **par point** et non par issue : au premier run, 3 questions sur 3 sujets différents auraient déclenché une escalade à tort. Trancher : un sujet par point (`#2/wasm-outdir`) ou un `round` remis à 1 sur une nouvelle question.
- [ ] Politique : un commit appartient au rôle du passage où il est apparu (Choreographer et Dancer partagent la branche de Rehearsal). **Sujet à traiter à part.** Piste, le message, l'auteur ou un trailer étant falsifiables :
  - le Conductor relève l'état du repo à chaque relais (lancement, `ask`, `reply`, `worker_done`) ;
  - au `ask` du Dancer, la politique vérifie aussi l'arbre non commité (rien dans ses zones interdites, sinon le Choreographer l'embarquerait) ;
  - au retour du Choreographer, ses commits ne touchent qu'ADR et `AGENTS.md`, et l'arbre non commité est identique au relevé d'avant ;
  - un registre des commits (sha → rôle), hors du worktree, vérifié avant la Premiere : un commit inconnu bloque le merge ;
  - limite : tient tant que le Dancer ne peut pas écrire dans le dossier du Conductor (couche 2). La signature par rôle : voir PRD §17.
- [ ] Tests sur des repos jouets.

**Fini quand** : chaque violation du PRD §5.3 est détectée par un test.

## Étape 6 — Le Conductor séquentiel, Piece v0 `hybrid-track`

- [x] Créer le remote GitHub d'antimurphy.
- [x] Créer le worktree et la branche `rehearsal/<ID>` depuis `origin/main` (`orca worktree create`) ; les supprimer après la Premiere (0.9.0).
- [x] Publier chaque échange : questions et réponses en commentaires de l'issue, rapports du Dancer et verdicts du Critic sur la PR (0.9.0).
- [ ] Skill `conductor` : lance le Choreographer sur une feature prête, route ses questions au Dramaturg (Orca `ask`/`reply`, Choreographer gardé éveillé), escalade au-delà de `max_exchange_rounds`, journalise les rapports, enchaîne Dancer → Critic.
  - [x] v0 (0.9.0) : skill fin ; tout passe par `ballet_rehearsal.py` (`begin`, `receive`, `premiere`, `status`), qui tient l'état, décide la suite (`NEXT: wait | escalate | done`) et appelle git, gh et Orca. Part d'une issue existante : Dancer si le plan a ses tâches, Choreographer sinon. Un rôle déjà lancé reçoit la suite dans sa session (`send`), une question reçoit sa réponse par `reply` : les contextes sont gardés.
  - [x] Premier run réel : FEAT-001.2 (#3) d'antimurphy, PR #9. 8 min en auto, aucune question, un seul tour de Critic ; `ESCALATE` sur la seule taille (1623 lignes > 700), le Director a mergé à la main.
  - [ ] Retours du premier run :
    - [x] Taille de diff comptée par le script, pas par le Critic : `git diff --shortstat origin/main...` après le rapport du Dancer. Clé `[escalation] diff_exclude` (globs : lockfiles, `tests/`…) ; le Critic ne juge plus la taille. Fait : `ballet_size.py`, `git diff --numstat origin/main...<branche>` (ajoutées + supprimées, binaires à 0) ; défaut `["*.lock", "pnpm-lock.yaml", "package-lock.json"]`. Vérifié sur la PR #9 : 1620 lignes comptées, 3 exclues (`Cargo.lock`) (0.12.0).
    - [x] `[escalation] max_diff_strict` : `false`, la taille est notée dans la PR et ne bloque rien ; `true`, la PR est ouverte quand même, libellé `ballet:oversized`, escalade **avant** le Critic (pas de review payée pour une slice qu'on redécoupe). Le Director débloque par le libellé `ballet:size-accepted`, la reprise lance alors le Critic. Fait : `ballet:oversized` posé au-delà, retiré en deçà, dans les deux modes ; un refus du Director (`ballet:rejected` + commentaire) renvoie au Dancer ; une taille acceptée le reste pour la Rehearsal (0.12.0).
    - [x] Journaliser la taille à **chaque** comptage, pas seulement au dépassement : événement `diff-size` (lignes comptées, lignes exclues, seuil, mode strict ou non, dépassé ou non). Sans les cas sous le seuil, pas de taux. Fait, avec le tour ; `status` montre la dernière mesure (0.12.0).
    - [x] Verdict en libellé de la PR (`ballet:approved | rejected | escalated`), posé par le script à chaque verdict, `ballet:escalated` à chaque escalade avec une PR (sauf sur une approbation en vigueur : CI en cours) ; la review et le commentaire « Verdicts » restent pour la lecture. Le libellé seul fait foi : `merge` exige `ballet:approved` posé après le dernier commit (timeline de la PR) ; s'il en reste plusieurs, le dernier posé l'emporte (0.10.0).
    - [x] Commande `resume <ID>` : le Director pose son libellé puis dit « reprends ». `approved` → Premiere ; `rejected` + les commentaires de PR postérieurs à la dernière escalade → le Dancer, dans sa session, sans compter d'aller-retour ; rien de décidé, ou un refus sans commentaire → l'escalade reste. Décision journalisée (`director-decision`) ; `status` montre le libellé en vigueur (0.10.0).
    - [x] Section Escalation du skill Conductor : décrire `resume` ; le Conductor ne merge ni ne pose de libellé à la place du Director (0.10.0).
    - [ ] Vérifier `label` sur un vrai repo à la prochaine Rehearsal : création des libellés, `--remove-label` d'un libellé absent de la PR.
    - [x] Notes non bloquantes du Critic : prises par le Dancer en **un seul commit**, après les points bloquants sur un refus ; sur un `APPROVED` avec notes, un tour de notes (commit unique du Dancer, le Critic ne relit que lui, sans nouvelle note), une seule fois, hors `max_round_trips`. Une note déclinée l'est avec sa raison (`## Notes declined`). Pas d'issue de suivi (0.13.0).
    - [ ] Plus tard : une troisième catégorie du Critic, à côté des points bloquants et des notes : opportunité, vigilance, bug détecté hors du diff… À verser au backlog du Dramaturg ; le circuit reste à définir.
    - [x] `receive <ID> --message <msg-id>` lit le message chez Orca (`orchestration inbox --full --json` : id, type, corps entier) ; une question garde son id pour la réponse ; un `escalation` d'Orca (worker arrêté) escalade avec ce qu'Orca en dit. Le Conductor n'écrit plus que la réponse du Director (0.13.0).
    - [x] `NEXT: escalate` sort avec 0 (cas prévu, pas une erreur) ; code ≠ 0 réservé aux pannes du script (0.9.1).
    - [x] `status` lisible : PR, verdict, CI, allers-retours, questions en attente, workers, dernier `NEXT` ; le JSON derrière `--json` ; le statut repasse à `open` quand une réponse du Director relance la Rehearsal (0.9.1). La taille viendra avec le lot 3.
    - [x] TDD vérifiable : le rapport du Dancer cite, par tâche, son test rouge et la ligne d'échec ; le Critic vérifie que l'échec est le bon, une tâche sans rouge est un point bloquant (0.13.0).
    - [x] `.ballet/run/` ignoré par `init-project` dans le `.gitignore` du projet, au lieu du `.gitignore` que le script écrit dans le dossier (0.9.1).
    - [x] Ménage antimurphy : worktree `rehearsal-FEAT-001-2` supprimé, FEAT-001.2 passé à `done` avec sa trace au journal, `.ballet/run/` ajouté au `.gitignore` (à la main).
    - [x] Retour du run FEAT-001.3 (#10) : un libellé de verdict déjà posé est retiré puis reposé, sinon GitHub garde sa vieille date et `merge` refuse l'APPROVED du tour de notes (0.13.1).
    - [x] Un merge refusé après un verdict escalade sans perdre les lignes `- …` déjà faites (verdict publié, libellé) (0.13.1).
    - [x] `receive <ID> --dispatch <ctx-id>` : le réveil d'un `worker_done` ne nomme que le dispatch ; le script lit le dernier message de ce worker (0.13.1).
    - [x] Le fil d'une note se retrouve par sa ligne d'origine (`originalLine`) quand le commit qui la corrige l'a déplacée (0.13.1).
    - [x] Retour du run FEAT-001.4 (#11) : la Premiere attend une CI en cours au lieu d'escalader. `merge` distingue une CI en cours (`CiPending`) d'une CI rouge ; la Premiere sonde toutes les 15 s jusqu'à `[escalation] ci_wait_seconds` (480 par défaut, sous la limite de 10 min d'un appel du Conductor), puis escalade ; une CI rouge escalade tout de suite (0.14.0).
    - [x] Retour du run FEAT-001.4 (#11) : un worker qui finit son tour sans `worker_done` (`escalation` d'Orca, `stopReason: finished`) est relancé une fois par le script pour envoyer son rapport ; une seconde fois, ou un arrêt sur erreur, escalade. La spec du worker dit d'envoyer `worker_done` au lieu de laisser croire que le message final y suffit (0.14.0).
    - [x] Vérifié sur FEAT-001.5 (#12) : la relance d'un worker (`nudge` du Critic au journal), la fermeture de la parente #1 après la dernière slice. Première Rehearsal mergée sans intervention.
    - [x] Vérifier l'attente de la CI (`waited Ns for the CI`) : vue sur FEAT-003 et FEAT-002 (45 à 75 s).
    - [x] Une preuve déterministe entre le Dancer et le Critic : au rapport du Dancer, après la politique et avant le push, le script lance la preuve du profil dans le worktree (`proof-start` à son début, `proof-end` à sa fin avec statut et durée, comme `handoff` et `message` pour un agent). Rouge ou worktree sali : rien n'est poussé, le Critic n'est pas lancé, le Dancer reprend avec les 60 dernières lignes ; au-delà de `max_round_trips` preuves rouges, ou après `proof_timeout_seconds` (420), escalade (0.24.0). À voir : le Critic relance encore la preuve lui-même ; on pourra le lui épargner une fois la preuve du script éprouvée.
    - [ ] Un test de mutation déterministe, nœud après la preuve (rapport du Dancer → politique → preuve → mutation → push/PR → taille → Critic). **Ballet porte la méthode, le projet l'outil.**
      - Le projet : l'outil à une version figée (sur antimurphy, mise : `mise.toml` versionné, binaires dans le cache de mise, partagés par tous les worktrees), sa config (`.cargo/mutants.toml`, exclusions des équivalents avec leur raison), les sorties dans le `.gitignore`, et une entrée d'une ligne par outil dans le profil : `[[repos.<repo>.mutation]]` avec `name`, `command` (`mise exec -- cargo mutants --in-diff {diff}`), `config` (le fichier où s'excluent les équivalents) et `report` (`path`, `format`). Le profil s'édite à la main par le Director : aucun rôle ne l'écrit.
      - Ballet : le diff de la branche contre le merge-base d'`origin/main`, filtré par `paths` (facultatif) ; un outil sans changement est sauté ; le périmètre passé par placeholders (`{diff}` un fichier, `{files}`, `{ranges}` en `fichier:début-fin`) ; les outils l'un après l'autre, même après un rouge. `ballet_mutation.py run` fait la même chose à la main, pour un dev : un seul chemin.
      - **Le code de sortie décide**, rien d'autre : rouge, rien n'est poussé, le Critic n'est pas lancé, le Dancer reprend avec les survivants (du rapport normalisé, sinon la fin de la sortie) et le chemin du log entier ; au-delà de `max_round_trips`, ou après `[mutation] timeout_seconds` (une heure), escalade. Le Conductor n'analyse rien. Hors d'un appel de 600 s : le script lance la mutation détachée et répond `NEXT: wait` ; à la fin, elle réveille le Conductor par un message Orca (vérifié, voir plus bas).
      - Journal, une étape comme un agent (`handoff` puis `message`) : `mutation-start` à son début, `mutation-end` à sa fin, par outil, avec `passed`, `timed_out`, `head`, `seconds`, enrichi du rapport normalisé quand il est lisible (tués, survivants, invalides, score, survivants plafonnés ; liste entière dans `.ballet/run/<ID>/`). Ballet supprime l'ancien rapport avant le run. Le parsing ne bloque jamais : rapport absent ou illisible, l'événement part allégé avec la raison (`report: missing` ou `unreadable: …`). Lecteurs de `ballet_mutation.py` : `cargo-mutants` d'abord, puis `stryker`, `pit`.
      - **Feature flag** : le profil désactive la mutation sans retirer ses entrées (une table `[mutation]` à part, pas `[escalation]` : `enabled = true` et `timeout_seconds = 3600` par défaut dans le `config.toml` du plugin, validés par `ballet_config.py`). À `false`, le nœud ne lance rien et la Rehearsal continue, mais le journal le dit : `mutation-skipped` avec sa raison (`disabled in the profile`) ; même événement, autre raison, sans entrée déclarée ou quand le diff ne touche aucun outil. `ballet_mutation.py run` respecte le flag, avec une option pour forcer à la main.
      - La règle, dans Ballet et pas dans les projets (`ballet:tdd`, chargée par le Dancer et le Critic) : un survivant se tue par un test unitaire, jamais un e2e ; un équivalent s'exclut dans le `config` de l'outil, avec sa raison ; le Critic juge chaque exclusion. Plus tard, la politique signale les changements de ce fichier.
      - [x] Pilote à la main sur antimurphy (2026-11-18), worktrees jetables, outils installés dans le worktree (rien en global).
        - Rust, cargo-mutants 27.1.0 (`cargo install --locked --root .tools`, 85 s), diff de FEAT-002.2 (466 lignes) passé tel quel (`--in-diff`) : 28 mutants, **151 s à froid, 155 s à chaud** (pas de cache : il recopie et rebâtit), code de sortie 2 sur un survivant. 10 survivants, 12 tués, 6 non compilables ; **les 10 sont de vrais trous de test**, aucun équivalent : `purpose_rank` (l'ordre des kits par usage) et 8 bras de la table des diacritiques (seuls `à` et `œ` testés). Le Critic avait approuvé. Rapport `mutants.out/outcomes.json` (totaux et liste), lisible sans effort.
        - TS, StrykerJS 10.1.1 + runner Vitest en dépendances de dev d'`apps/web`, diff de FEAT-002.4. Trois frictions : TypeScript 7 n'a plus l'API JS dont Stryker réécrit le `tsconfig` (`tsconfigFile` vers un fichier absent) ; pnpm cache le runner au chargeur de plugins (`plugins` en chemin explicite) ; le bac à sable ne copie que le dossier lancé, sans `tsconfig.base.json` (lancer depuis la racine, `ignorePatterns` pour `target`, `crates`, `.agents`…, et une config Vitest dont la racine revient à `apps/web`). Fichiers entiers : 118 mutants, 74 s, 7 survivants dont 6 hors du diff. **Limité aux lignes du diff** (`mutate: ["fichier:début-fin"]`) : 31 mutants, **27 s à froid**, 1 survivant, vrai (le champ de recherche vide au départ n'est pas testé). **À chaud, 10 s** (cache incrémental, 118 sur 118 repris). Code de sortie 1 avec `thresholds.break = 100`.
        - Pas essayé : `apps/worker` (pool Cloudflare de Vitest), l'e2e.
        - Conclusions : moins de 3 min par slice ici, le code de sortie est fiable des deux côtés, aucun bruit d'équivalents (11 survivants, 11 vrais trous). Le diff limité aux lignes changées est indispensable (6 survivants sur 7 hors du diff sinon) : c'est Ballet qui le calcule et le passe. Le budget d'une heure reste, pour des projets plus gros. Le front plus tard (contournements TypeScript 7, pnpm, bac à sable).
      - [x] Le nœud dans Ballet (0.25.0). Spike d'abord (2026-11-18) : un processus détaché, qui n'est pas un worker, mais avec l'environnement hérité du Conductor, réveille le Conductor par `orca orchestration send --to run:<runId> --type status`, au repos comme en plein tour ; sans cette identité, Orca refuse (`no_active_sender_terminal`). Le `runId` est lu sur le dispatch du Dancer (`worker-show`). Le repli par Bash en arrière-plan n'a pas servi.
        - `ballet_rehearsal.py` : la preuve verte, `_launch_mutation` lance `mutate <ID>` (interne) détaché et répond `NEXT: wait` ; à sa fin, les résultats dans `.ballet/run/<ID>/mutation-<tour>.json` et un message Orca (`<ID> · mutation done`, payload `{"ballet": "mutation", …}`, `mutation-wake` au journal). Le Conductor le reçoit comme les autres (`receive --message`) : vert, push, PR, rapport du Dancer publié, taille, Critic ; rouge, le Dancer reprend avec les survivants, le log et le fichier des équivalents (`red_mutations`, au-delà de `max_round_trips` escalade). Escalade aussi : trop long, panne en arrière-plan (le réveil part quand même), worktree qui a bougé pendant la mutation. Un réveil d'un autre tour est ignoré ; `receive --mutation` rattrape un réveil perdu ; `status` montre la mutation en cours.
        - `ballet_mutation.py` : `run [--force]`, le diff et son filtre `paths` (fnmatch sur le chemin entier), les plages (lignes `+` côté branche), les placeholders quotés, le budget commun, le lecteur `cargo-mutants` (format vérifié sur un vrai run de 27.1.0, fixture `tests/fixtures/cargo-mutants-27.1.0-outcomes.json`).
        - `[mutation] enabled` et `timeout_seconds`, les entrées `[[repos.<repo>.mutation]]` validées par `ballet_config.py` ; la règle dans `ballet:tdd` ; skills Dancer, Critic, Conductor ; PRD, README.
      - Étapes suivantes : dans antimurphy, la TASK du Choreographer (ADR 0007 mise, `mise.toml`, `.cargo/mutants.toml`, `.gitignore`) et la CI passée à mise à la main ; dans Ballet, la Scène (`mutation-*` au fil), les recettes par stack dans `init-project`, les lecteurs `stryker` et `pit` ; puis l'entrée `mutation` du profil d'antimurphy, à la main.
    - [ ] À affiner : les notes déclinées adressées au Choreographer (amender une décision, fixer un contrat pour la tranche suivante) se perdent dans les commentaires de la PR au merge. Les lui porter, ou les reporter sur l'issue parente ou la tranche suivante ; le circuit reste à définir.
    - [ ] Plus tard : taille des tranches. #3 puis #10 au-delà du double de `max_diff_lines` (700) ; la taille est journalisée (`diff-size`), on tranchera sur ces mesures entre le découpage du Choreographer et le seuil. Premier pas (0.20.0) : une slice vise la moitié du seuil, tests compris, et se redécoupe au-delà des deux tiers ; le seuil est donné au Choreographer dans sa consigne. Mesuré sur FEAT-003 et FEAT-002 (antimurphy, seuil 700) : 8 slices, dont 4 sans critère, découpées par couche (API, client, écran) ; FEAT-003 tenait en 2. Second pas (0.23.0) : le moins de slices possible, chacune estimée sous les deux tiers du seuil et verticale (au moins un critère entier de bout en bout) ; une slice sans critère seulement pour le walking skeleton ou un critère qui seul dépasse le seuil ; fusionner deux voisines tant que la fusion tient sous les deux tiers. À mesurer sur la prochaine feature.
    - [ ] Le Choreographer vérifie l'outillage dont dépend son plan (version, comportement) par un spike, plutôt que de reprendre AGENTS.md (isolation D1 de `@cloudflare/vitest-plugin` 1.8.2).
  - [x] Une liste d'issues à dépiler (`/ballet:hybrid-track #4 #5 #6`) : une Rehearsal après l'autre, la suivante part de `main` après la Premiere de la précédente ; une escalade arrête la liste. Fait : `ballet_rehearsal.py run <éléments…> [--plan review|auto]`, état `.ballet/run/queue.json` ; c'est le script qui ouvre la suivante à la Premiere (le Conductor ne fait que suivre `NEXT`, il n'a pas de logique de file à tenir) ; `resume` reprend la Rehearsal puis la file, ou rouvre l'élément devant lequel la file s'est arrêtée ; `status` montre la file ; `<ID>` facultatif (la Rehearsal en cours) ; `begin <élément>` est une file d'un élément (0.18.0).
  - [x] Partir d'une feature prête (Choreographer qui crée l'issue), Dramaturg consulté. Fait : `run FEAT-002` ouvre une Rehearsal de planification (branche `rehearsal/FEAT-002`, le Choreographer seul) ; à son rapport (`- Issue: #N`, `Outcome: planned | sliced | blocked`), le script lit l'issue et ses slices sur GitHub (liste des issues ouvertes, pas la recherche, en retard) et les met en tête de file ; la première prend le worktree (branche renommée, commits du Choreographer `owned`, son dispatch gardé pour les questions du Dancer). Une issue sans plan suit le même chemin : l'escalade « has no tasks (slices?) » n'existe plus. Une question au Dramaturg sans issue n'est que journalisée (0.19.0). Le Choreographer en mode auto : consigne et section du skill (0.20.0).
  - [x] `--plan review` (défaut, `[escalation] plan_approval = true`) : la file s'arrête après la publication du plan ; le Director pose `ballet:plan-approved` (créé d'avance par le script) sur l'issue planifiée, puis `resume` lance le Dancer. `--plan auto` enchaîne (0.19.0).
  - [x] Vérifier sur un vrai run (FEAT-002 d'antimurphy) : le renommage de la branche du worktree sous Orca (`git branch -m`, puis `orca worktree rm --delete-branch`) ; s'il casse, repli : la slice 1 garde la branche de la planification (`rehearsal/FEAT-002`), l'état retient la branche au lieu de la déduire de l'ID, les slices suivantes gardent leur nom, le Choreographer gardé éveillé dans le worktree renommé, la planification sur le `main` laissé par la feature précédente.
  - [ ] Pas encore géré : modifier un plan en cours de validation (`--plan review`). Aujourd'hui, le Director l'édite à la main sur l'issue, ou abandonne la file en supprimant `.ballet/run/queue.json`. À prévoir : renvoyer le plan au Choreographer avec ses remarques, dans sa session.
  - [ ] Pas encore géré : relancer par erreur une feature déjà planifiée (`run FEAT-002` une seconde fois) : le Choreographer recréerait son issue. À prévoir : chercher l'issue existante de la feature avant d'ouvrir la planification, et jouer ses slices ouvertes.
  - [ ] Pas encore géré : passer une issue parente dans la file (`run #13`) : sans tâches propres, elle repart en planification au lieu de jouer ses slices. À prévoir : une parente qui a des slices ouvertes se déroule en ses slices, dans l'ordre.
  - [ ] Multi-repos (v0 : un seul repo).
- [x] Slices : publier une issue par slice, liée à l'issue parente ; enchaîner leurs Rehearsals dans l'ordre (0.19.0) ; fermer la parente avec la dernière.
  - [x] La Premiere ferme l'issue elle-même (le `Closes #N` de la PR est implicite, et absent d'une PR ouverte à la main : #2 d'antimurphy était restée ouverte), puis la parente quand plus aucune slice (`Part of #<parente>` en première ligne) n'est ouverte ; un échec n'annule pas la Premiere, il se signale (0.11.0).
  - [ ] Plus tard : les sous-issues natives de GitHub plutôt que la ligne `Part of` et la recherche (avancement visible sur la parente).
- [x] Politique après chaque rôle ; renvoi une fois, escalade à la deuxième violation. Rien n'est poussé en violation ; un Critic en violation, ou un Choreographer qui répond hors de ses fichiers, escalade tout de suite ; chaque passage journalisé (`policy`) (0.15.0).
- [x] Plafond de 2 allers-retours Dancer ↔ Critic (0.9.0).
- [ ] Déclencheurs d'escalade mécaniques dès la v0 (l'auto en dépend) : taille de diff, zone sensible, test modifié ou supprimé, `VERDICT: ESCALATE`, seconde violation. Déjà là (0.9.0) : `VERDICT: ESCALATE`, plafonds de tours et d'allers-retours, question au Director, opération GitHub refusée, message invalide ; taille de diff en mode strict (0.12.0) ; zone sensible, test supprimé ou renommé, seconde violation (0.15.0).
- [x] Premiere : merge de la PR par rebase si `APPROVED` postérieur au dernier commit et CI verte ; une CI absente bloque (0.9.0). La politique s'y ajoutera.
- [x] Antimurphy : workflow GitHub qui lance `pnpm proof` sur chaque PR (Director, à la main).
- [ ] Journal d'événements JSONL (format à figer). v0 : `.ballet/run/journal.jsonl` (`at`, `rehearsal`, `event`, `detail`), à côté de l'état `.ballet/run/<ID>.json` (0.9.0).
- [x] Commande `/ballet:hybrid-track #<issue>` (0.9.0).

**Fini quand** : le Director cadre, lance `/ballet:hybrid-track`, et l'issue arrive sur `main` sans intervention, ou escalade avec son motif.

## Étape 7 — Runs réels

- [ ] 3 à 5 issues d'antimurphy en `hybrid-track`.
- [ ] Lire le journal : refus du Critic, allers-retours, builds rouges, merges à corriger après coup.
- [ ] Ajuster les specs de rôles et les seuils.

**Fini quand** : on a un avis chiffré sur la qualité du Critic.

## Ensuite (à découper le moment venu)

- [ ] Ranger le profil à la fin des travaux de la méthode : une table par étape (`[proof] timeout_seconds` au lieu de `[escalation] proof_timeout_seconds`, comme `[mutation]`) ; `plan_approval`, choix de workflow et non seuil, hors de `[escalation]`. `[escalation]` ne garde que les seuils qui font remonter au Director. Casse les profils existants : migration à prévoir (`init-project`).
- [ ] La Scène (monitoring, PRD §12) : le concept existe (`python3 scripts/ballet_stage.py <home>` ou `--scan <dossier>`, puis http://127.0.0.1:7700). v3, volontairement basique après deux maquettes visuelles écartées : par projet, les Rehearsals (en cours d'abord), le rôle en cours, et le fil du journal (passages `handoff` du Conductor vers les workers, messages reçus avec leur texte entier, pas du script). v4 (0.22.0) : la file de la Piece (jouées, en cours, à venir, titres des issues en attente, plan review ou auto), ce que le Director doit faire sur une escalade (plan à approuver, taille, PR à trancher, question), les phases (plan, code, revue, Premiere), allers-retours et taille du diff face aux seuils du profil, le fil en échanges et pas du script (filtres, textes repliés, verdicts et issues en couleur), la planification d'une feature rattachée à sa première slice (`planned_by`), clair et sombre. À travailler, une fois l'usage éprouvé : valider le nom « Scène » au vocabulaire (PRD §3), les temps par phase et la comparaison des modèles, un registre de projets.
- [ ] Dancer Claude puis Dancer Mistral sur les mêmes issues, et comparaison (PRD §15.4).
- [ ] Workshop auto : `auto-track`.
- [ ] Déclencheurs d'escalade subtils : désaccord persistant, build instable.
- [ ] Projet multi-repos.
- [ ] `parallel-conductor` : `hybrid-parallel` (file de merge et conflits : principes au PRD §7).
  - Déjà isolé par Rehearsal : son ID, son worktree, son état `<ID>.json`, son dossier `.ballet/run/<ID>/` (specs des workers, logs de preuve et de mutation), ses dispatches. À reprendre : la file à une seule Rehearsal `current` et l'ID facultatif des commandes (explicite en parallèle) ; les écritures concurrentes du journal ; les ports des preuves e2e lancées en même temps ; un plafond de tâches lourdes simultanées (preuve, mutation) sur la machine ; les caches partagés (mutation, `target/`) sans écriture concurrente.
- [ ] Workshop discovery, en propositions d'abord.
- [ ] Migration de Flownest.
