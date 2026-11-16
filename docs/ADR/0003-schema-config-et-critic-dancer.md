# ADR 0003 — Schéma de `.ballet/config.toml` et règle « Critic ≠ Dancer »

- Statut : acceptée (à ajuster à l'usage)
- Date : 2026-11-15
- Source : étape 3 (`TASKS.md`), scripts `scripts/ballet_config.py` et `scripts/init_project.py`, tests dans `tests/`.

## Schéma (défauts dans `config.toml` du plugin, surcharge clé par clé dans le projet)

| Clé | Règle | Défaut |
|---|---|---|
| `[project] specs` | texte, **obligatoire** (espace du Dramaturg) | — |
| ~~`[project] merge`~~ | retirée par l'ADR 0004 : Ballet intègre toujours par PR | — |
| `[project] specs_language` | code de langue (`en`, `fr`…) ; langue des specs, le code reste en anglais | `"en"` |
| `[project] adr` | texte, dossier des ADR, où seul le Choreographer écrit | `"docs/ADR/"` |
| `[project] rules` | liste de noms de skills du plugin (un nom inconnu est refusé) | `[]` |
| `[repos.<nom>] path`, `proof` | texte, **obligatoires** ; au moins un repo | — |
| `[repos.<nom>] needs` | liste de repos déclarés ; pas de cycle | `[]` |
| `[roles.<rôle>] cli` | rôle parmi `dramaturg`, `choreographer`, `dancer`, `critic` ; CLI parmi `claude`, `grok`, `mistral-vibe`, `codex`, `opencode`, `gemini-cli`, `kimi` | tous `claude` |
| `[roles.<rôle>] model` | texte, facultatif (alias du CLI, ex. `opus`, `sonnet`) | Choreographer et Critic `opus`, Dancer `sonnet`, Dramaturg absent (défaut du CLI) |
| `[policy] sensitive_zones` | liste de globs | `[]` |
| `[escalation] max_round_trips`, `max_diff_lines` | entiers positifs | 2, 400 |

Fusion : une table se fusionne clé par clé ; toute autre valeur (liste comprise) est remplacée par celle du projet.

## Décision « Critic ≠ Dancer avec surcharges »

Vérifiée sur la configuration fusionnée, par le script, avant tout lancement :
- CLI différents : accepté ;
- même CLI : accepté **seulement si les deux rôles ont un `model` explicite et différent**.

Le script ne sait pas dire si deux modèles sont de « familles » différentes : il n'impose que la différence explicite. Si on veut interdire par exemple deux modèles d'une même famille, il faudra une table de familles (à décider quand le cas se présentera).

## Routage par défaut (2026-11-15)

Tous les rôles sur Claude pour commencer : Dancer en `sonnet`, Choreographer et Critic en `opus`. « Critic ≠ Dancer » est respecté par la différence de modèle. Mistral (Dancer) et Grok (Critic) reviennent par surcharge quand on rejouera les comparaisons (PRD §15, étape 4).

## Conséquences

- Aucune règle de `trunk-based` n'existe encore comme skill : mettre `"trunk-based"` dans `rules` est refusé tant qu'elle n'est pas écrite.
- `init-project` ne gère que le mono-repo ; le multi-repos se complète à la main puis se vérifie avec `ballet_config.py check` (étape 6 du plan).
- La commande de preuve d'antimurphy est un **marqueur qui échoue volontairement** (`echo "proof non définie" && exit 1`) : le projet n'a pas encore de code. À remplacer.
