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
  - [ ] Premier run réel sur FEAT-001 d'antimurphy.
    - [x] Slice #2 (walking skeleton) : 7 tâches, preuve verte, 3 questions au Choreographer.
  - [x] Chaque Rehearsal sur sa branche `rehearsal/<ID>`, dans son worktree, intégrée par une PR que le Conductor merge par rebase ; le Critic rend ses remarques en un lot, publiées en une review ; sur un refus, le Dancer relit la PR ; clé `[project] merge` retirée (ADR 0004, 0.7.0).
- [ ] `critic` : rend un verdict (message `type: verdict`, première ligne `VERDICT: …`), en lecture seule.
- [ ] Les règles communes minimales chargées par chaque rôle (tdd, clean code, trunk-based).

**Fini quand** : une feature d'antimurphy passe à la main de l'état prêt au code validé.

## Étape 5 — Les scripts déterministes

- [ ] Script de politique : état git avant et après, zones interdites, périmètre par rôle (dont ADR, `AGENTS.md` et branches `spike/*` réservés au Choreographer), état GitHub de l'issue inchangé.
- [ ] Script GitHub : la liste fermée d'opérations (PRD §5.4), chaque appel journalisé. Déjà là : `read`, `publish`, `plan`, `slice` (0.5.0). À ajouter (ADR 0004) : pousser la branche de Rehearsal, ouvrir la PR, `read-pr` (PR et reviews), publier une review, commenter l'issue et la PR, merger par rebase, supprimer la branche mergée.
- [ ] Lecture de l'en-tête JSON des messages (`message.md`), renvoi d'un en-tête invalide, compte des tours par sujet et paire de rôles.
- [ ] Compter les tours **par point** et non par issue : au premier run, 3 questions sur 3 sujets différents auraient déclenché une escalade à tort. Trancher : un sujet par point (`#2/wasm-outdir`) ou un `round` remis à 1 sur une nouvelle question.
- [ ] Politique : un commit appartient au rôle du passage où il est apparu (Choreographer et Dancer partagent la branche de Rehearsal).
- [ ] Tests sur des repos jouets.

**Fini quand** : chaque violation du PRD §5.3 est détectée par un test.

## Étape 6 — Le Conductor séquentiel, Piece v0 `hybrid-track`

- [ ] Créer le remote GitHub d'antimurphy.
- [ ] Créer le worktree et la branche `rehearsal/<ID>` depuis `main` avant le Choreographer ; les supprimer après la Premiere.
- [ ] Publier chaque échange : questions et réponses en commentaires de l'issue, rapports du Dancer et verdicts du Critic sur la PR.
- [ ] Skill `conductor` : lance le Choreographer sur une feature prête, route ses questions au Dramaturg (Orca `ask`/`reply`, Choreographer gardé éveillé), escalade au-delà de `max_exchange_rounds`, journalise les rapports, enchaîne Dancer → Critic.
- [ ] Slices : publier une issue par slice, liée à l'issue parente ; enchaîner leurs Rehearsals dans l'ordre ; fermer la parente avec la dernière.
- [ ] Politique après chaque rôle ; renvoi une fois, escalade à la deuxième violation.
- [ ] Plafond de 2 allers-retours Dancer ↔ Critic.
- [ ] Déclencheurs d'escalade mécaniques dès la v0 (l'auto en dépend) : taille de diff, zone sensible, test modifié ou supprimé, `VERDICT: ESCALATE`, seconde violation.
- [ ] Premiere : merge de la PR par rebase si `APPROVED`, politique et CI vertes.
- [ ] Journal d'événements JSONL (format à figer).
- [ ] Commande `/ballet:hybrid-track`.

**Fini quand** : le Director cadre, lance `/ballet:hybrid-track`, et l'issue arrive sur `main` sans intervention, ou escalade avec son motif.

## Étape 7 — Runs réels

- [ ] 3 à 5 issues d'antimurphy en `hybrid-track`.
- [ ] Lire le journal : refus du Critic, allers-retours, builds rouges, merges à corriger après coup.
- [ ] Ajuster les specs de rôles et les seuils.

**Fini quand** : on a un avis chiffré sur la qualité du Critic.

## Ensuite (à découper le moment venu)

- [ ] Dancer Claude puis Dancer Mistral sur les mêmes issues, et comparaison (PRD §15.4).
- [ ] Workshop auto : `auto-track`.
- [ ] Déclencheurs d'escalade subtils : désaccord persistant, build instable.
- [ ] Projet multi-repos.
- [ ] `parallel-conductor` : `hybrid-parallel` (file de merge et conflits : principes au PRD §7).
- [ ] Workshop discovery, en propositions d'abord.
- [ ] Migration de Flownest.
