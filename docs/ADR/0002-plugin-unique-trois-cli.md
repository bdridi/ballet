# ADR 0002 — Un seul plugin pour les trois CLI

- Statut : acceptée, réserve sur Grok
- Date : 2026-11-15
- Source : étape 2 (`TASKS.md`), commit `8fab504`.

## Décision

Le repo `ballet` est directement un plugin Claude Code (`.claude-plugin/plugin.json`, `skills/`), avec une marketplace locale (`.claude-plugin/marketplace.json`, nom `ballet-local`) pour le test. Les règles communes (`tdd`, `bdd`, `ddd`, `clean-code`) sont **des skills** d'un fichier chacun, `skills/<règle>/SKILL.md` : c'est la seule forme que les trois CLI découvrent et que le Conductor peut nommer dans une spec (PRD §10.3). Elles sont volontairement minimales, à faire évoluer.

## Installation, par CLI (vérifiée)

| CLI | Commande | `/ballet:dramaturg` | `/dramaturg` seul |
|---|---|---|---|
| Claude | `claude plugin marketplace add <repo>` puis `claude plugin install ballet@ballet-local` | oui | oui |
| Mistral Vibe | pas de commande : lien `~/.vibe/plugins/ballet` → repo | oui | oui |
| Grok | `grok plugin install <repo> --trust` | **non testé** (limite d'usage gratuit) ; plugin reconnu, 1 dossier de skills | non testé |

Pour tester sans installer : `claude --plugin-dir <repo>`.

## Conséquences

- Les trois CLI voient les cinq skills sans conversion : un seul plugin les sert (Grok à confirmer).
- `/dramaturg` sans préfixe est accepté tant qu'il n'y a pas d'ambiguïté ; les specs et la doc écrivent toujours `/ballet:dramaturg`.
- Grok demande `--trust` à l'installation ; Vibe demande l'approbation du dossier du projet, pas celle du plugin.
- Le validateur de Claude signale l'absence d'icône : sans effet tant que le plugin n'est pas publié.
- Installés sur la machine de test : plugin Claude (user), plugin Grok, lien Vibe. Désinstallation : `claude plugin uninstall ballet@ballet-local`, `grok plugin uninstall ballet`, supprimer le lien.
