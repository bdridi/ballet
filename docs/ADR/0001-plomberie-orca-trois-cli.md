# ADR 0001 — Plomberie Orca avec Claude, Grok et Mistral Vibe

- Statut : acceptée
- Date : 2026-11-14
- Source : spike 1 (PRD §15.1), branche `spike/01-plomberie`, commits `6836078` et suivant (Mistral validé), note détaillée `spikes/01-plomberie.md` sur cette branche.

## Contexte

Le PRD suppose qu'un worker Orca lancé avec n'importe lequel des trois CLI reçoit une spec, voit les skills, sait appeler `ask` et `worker_done`, et accepte des permissions imposées. Le spike l'a vérifié sur une tâche bidon.

## Constats

- **Claude** : tout fonctionne (skill natif, `ask`, `worker_done`).
- **Grok** : `ask` et `worker_done` fonctionnent. Le skill projet n'est pas vu nativement (hypothèse : dossier non approuvé, non vérifiée). `--deny "Bash(gh:*)"` est vérifié.
- **Mistral Vibe** : tout fonctionne (skill natif via `.agents/skills`, `ask`, `worker_done`) après authentification. Orca n'a pas de session structurée pour lui (terminal agent). Il demande une approbation de dossier interactive au premier lancement. Une première tentative, avant authentification, a échoué (prompt collé dans zsh, erreur « Invalid API key » trompeuse) ; sa cause exacte n'est pas établie.

## Décision

1. La méthode du PRD tient pour Claude et Grok : on garde les workers Orca et la communication en étoile via `ask` / `worker_done`.
2. Les trois CLI sont utilisables comme workers. Le Dancer démarre sur Claude (référence du PRD §9), puis Mistral à l'étape 4.
3. Le lien `.agents/skills` → `.claude/skills` est retenu pour Vibe (vérifié).
4. Pour les permissions, on compte sur les réglages du CLI **plus** la politique déterministe du Conductor, jamais sur les réglages seuls (déjà dit au PRD §6).

## Conséquences

- `init-project` doit pré-approuver le dossier de confiance de Vibe (et vérifier celui de Grok), sinon un worker non interactif reste bloqué.
- Le Conductor doit traiter Vibe comme un worker en mode terminal (autre cycle de vie que Claude et Grok) et vérifier son lancement.
- À l'étape 2, tester le skill via le plugin (le spike n'a testé que des skills projet) et l'approbation de dossier côté Grok.
- Le PRD §17 est mis à jour sur : visibilité des skills par Vibe, lien `.agents/skills`, permissions par CLI (partielles).
