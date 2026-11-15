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

## Étape 3 — La config

- [ ] `config.toml` par défaut du plugin (routage par rôle, plafonds, seuils).
- [ ] Schéma de `.ballet/config.toml` (PRD §10.5), et réponse à la question « Critic ≠ Dancer avec surcharges ».
- [ ] Script de config : lire, fusionner clé par clé, vérifier (champs projet obligatoires, Critic ≠ Dancer, cycles et repos inconnus dans `needs`).
- [ ] Tests du script, sans agent.
- [ ] `init-project` minimal qui génère `.ballet/config.toml`, `AGENTS.md`, `CLAUDE.md` et le lien `.agents/skills`.
- [ ] Lancer `init-project` sur antimurphy.

**Fini quand** : antimurphy a sa config, et le script refuse les configs invalides.

## Étape 4 — Les rôles, un par un, lancés à la main

Sans Conductor : on ajuste chaque spec de rôle isolément, quand c'est encore facile.

- [ ] `dramaturg` : un vrai Workshop sur antimurphy, jusqu'au brouillon d'issue dans l'espace specs.
- [ ] `choreographer` : rend un plan, une section par repo, en lecture seule.
- [ ] `dancer` : exécute le plan en red → green → refactor, commite, preuve verte.
- [ ] `critic` : rend un verdict au format `VERDICT: …`, en lecture seule.
- [ ] Les règles communes minimales chargées par chaque rôle (tdd, clean code, trunk-based).

**Fini quand** : une issue d'antimurphy passe à la main du brouillon au code validé.

## Étape 5 — Les scripts déterministes

- [ ] Script de politique : état git avant et après, zones interdites, périmètre par rôle, état GitHub de l'issue inchangé.
- [ ] Script GitHub : la liste fermée d'opérations (PRD §5.4), chaque appel journalisé.
- [ ] Tests sur des repos jouets.

**Fini quand** : chaque violation du PRD §5.3 est détectée par un test.

## Étape 6 — Le Conductor séquentiel, Piece v0 `hybrid-track`

- [ ] Créer le remote GitHub d'antimurphy.
- [ ] Skill `conductor` : publie l'issue, enchaîne Choreographer → Dancer → Critic.
- [ ] Politique après chaque rôle ; renvoi une fois, escalade à la deuxième violation.
- [ ] Plafond de 2 allers-retours Dancer ↔ Critic.
- [ ] Déclencheurs d'escalade mécaniques dès la v0 (l'auto en dépend) : taille de diff, zone sensible, test modifié ou supprimé, `VERDICT: ESCALATE`, seconde violation.
- [ ] Premiere : merge auto sur `main` si `APPROVED` et politique verte.
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
- [ ] `parallel-conductor` : `hybrid-parallel`.
- [ ] Workshop discovery, en propositions d'abord.
- [ ] Migration de Flownest.
