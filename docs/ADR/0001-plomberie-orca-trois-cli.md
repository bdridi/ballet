# ADR 0001 — Plomberie Orca avec Claude, Grok et Mistral Vibe

- Statut : acceptée, avec une réserve sur Mistral Vibe (à lever avant l'étape 4)
- Date : 2026-11-14
- Source : spike 1 (PRD §15.1), branche `spike/01-plomberie`, commit `6836078`, note détaillée `spikes/01-plomberie.md` sur cette branche.

## Contexte

Le PRD suppose qu'un worker Orca lancé avec n'importe lequel des trois CLI reçoit une spec, voit les skills, sait appeler `ask` et `worker_done`, et accepte des permissions imposées. Le spike l'a vérifié sur une tâche bidon.

## Constats

- **Claude** : tout fonctionne (skill natif, `ask`, `worker_done`).
- **Grok** : `ask` et `worker_done` fonctionnent. Le skill projet n'est pas vu nativement (hypothèse : dossier non approuvé, non vérifiée). `--deny "Bash(gh:*)"` est vérifié.
- **Mistral Vibe** : voit le skill via `.agents/skills` (une fois le dossier approuvé), mais Orca ne sait pas le lancer proprement (pas de mode structuré, le prompt est collé dans zsh), il demande une approbation de dossier interactive, et la clé API n'était pas configurée. `ask` et `worker_done` non testés.

## Décision

1. La méthode du PRD tient pour Claude et Grok : on garde les workers Orca et la communication en étoile via `ask` / `worker_done`.
2. Pas de Dancer Mistral dans la configuration par défaut tant que le lancement Orca de Vibe n'est pas résolu. Le Dancer démarre sur Claude (déjà la référence du PRD §9) ; Mistral reste le candidat de l'étape 4.
3. Le lien `.agents/skills` → `.claude/skills` est retenu pour Vibe (vérifié).
4. Pour les permissions, on compte sur les réglages du CLI **plus** la politique déterministe du Conductor, jamais sur les réglages seuls (déjà dit au PRD §6).

## Conséquences

- Avant l'étape 4 : configurer la clé Mistral, tester `ask` / `worker_done` avec Vibe, trouver un lancement Orca fiable (prompt court + fichier, ou agent personnalisé Vibe), et pré-approuver le dossier de confiance dans `init-project`.
- À l'étape 2, tester le skill via le plugin (le spike n'a testé que des skills projet) et l'approbation de dossier côté Grok.
- Le PRD §17 est mis à jour sur : visibilité des skills par Vibe, lien `.agents/skills`, permissions par CLI (partielles).
