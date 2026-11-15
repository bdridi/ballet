# Ballet

Une méthode commune pour faire travailler des agents de code (Claude, Grok, Mistral Vibe) en chaîne, sur Orca.
Ballet est un plugin : on l'installe une fois, tous vos projets en profitent.

> État : en construction (v0.1). Aujourd'hui, le plugin fournit le skill `dramaturg`, les règles communes (`tdd`, `bdd`, `ddd`, `clean-code`) et l'amorçage d'un projet (`init-project`). La méthode complète est décrite dans [`PRD.md`](PRD.md), le plan dans [`TASKS.md`](TASKS.md).

## Prérequis

- macOS avec Orca installé et ouvert.
- Au moins un de ces CLI, authentifié : Claude Code (`claude`), Grok (`grok`), Mistral Vibe (`vibe`).
- Python 3.11 ou plus récent (bibliothèque standard uniquement).
- Un clone de ce repo, par exemple `~/Workspace/ballet`. Dans les commandes ci-dessous, remplacez `<chemin-vers-ballet>` par ce chemin.

## Installation

Une seule fois par CLI que vous utilisez.

### Claude Code

```sh
claude plugin marketplace add <chemin-vers-ballet>
claude plugin install ballet@ballet-local
```

Pour essayer sans installer : `claude --plugin-dir <chemin-vers-ballet>`.

### Mistral Vibe

Vibe n'a pas de commande d'installation : on lie le repo dans son dossier de plugins.

```sh
mkdir -p ~/.vibe/plugins
ln -s <chemin-vers-ballet> ~/.vibe/plugins/ballet
```

Au premier lancement dans un projet, Vibe demande d'approuver le dossier (« Trust this folder? ») : acceptez, sinon il ne charge ni `AGENTS.md` ni les skills du projet.

### Grok

```sh
grok plugin install <chemin-vers-ballet> --trust
```

(`--trust` : Grok exige un accord explicite pour installer un plugin. Ballet ne contient ni hook ni serveur MCP.)

## Vérifier l'installation

Dans l'un des CLI, lancez :

```
/ballet:dramaturg
```

Le Dramaturg doit se présenter. `/dramaturg` sans préfixe fonctionne aussi dans Claude et Vibe tant qu'aucun autre skill ne porte ce nom.

## Amorcer un projet

Dans le dossier d'accueil du projet (le repo unique, ou le repo de specs en multi-repos) :

```
/ballet:init-project
```

Le skill demande l'espace des specs et la commande de preuve (celle qui dit « c'est vert »), puis crée :

- `.ballet/config.toml` : le profil du projet (repos, preuve, règles, surcharges de routage) ;
- `AGENTS.md` et `CLAUDE.md` (qui importe `AGENTS.md`), sans écraser vos fichiers existants ;
- `.claude/skills/` et le lien `.agents/skills` vers ce dossier, pour que Vibe voie les skills du projet ;
- le skill projet `reset-ballet`, qui réinstalle le plugin depuis votre clone (voir *Mettre à jour*).

Pour vérifier la configuration à la main :

```sh
python3 <chemin-vers-ballet>/scripts/ballet_config.py check <dossier-du-projet>
```

## Mettre à jour

Après un `git pull` (ou une modification) dans le clone, lancez `/reset-ballet` depuis un projet amorcé, ou directement :

```sh
python3 <chemin-vers-ballet>/scripts/reset_plugin.py
```

Claude travaille sur une copie du plugin, qu'il ne rafraîchit pas tant que la version ne change pas : le script le désinstalle, le réinstalle et vérifie que la copie a tous les fichiers du clone. Pour Vibe, il refait le lien si besoin ; pour Grok, il lance `grok plugin update`. Redémarrez ensuite les sessions ouvertes.

## Désinstaller

```sh
claude plugin uninstall ballet@ballet-local
grok plugin uninstall ballet
rm ~/.vibe/plugins/ballet
```

## Développer Ballet

```sh
python3 -m unittest discover -s tests
```

Règles du repo : [`AGENTS.md`](AGENTS.md).
