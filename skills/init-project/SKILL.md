---
name: init-project
description: Amorce un projet pour Ballet (profil `.ballet/config.toml`, AGENTS.md, CLAUDE.md, lien `.agents/skills`). À utiliser une fois, dans le dossier d'accueil d'un projet, avant de lancer la chaîne, ou quand le Conductor refuse de démarrer faute de profil.
---

# init-project

Tu amorces le projet courant, qui doit être son dossier d'accueil (repo unique, ou repo de specs).

1. Demande au Director, s'il ne les a pas donnés :
   - l'**espace des specs** (un dossier, ex. `docs/` ou `specs/`) ;
   - la **commande de preuve**, celle dont le succès veut dire « c'est vert » (ex. `make test`).
2. Lance le script, qui se trouve à `../../scripts/init_project.py` par rapport au dossier de ce skill :

   ```sh
   python3 <chemin>/scripts/init_project.py . --specs "<specs>" --proof "<preuve>"
   ```

   Option : `--rules tdd,bdd` pour choisir les règles communes (défaut : `tdd,bdd,ddd,clean-code`), `--repo <nom>` pour nommer le repo.
3. Rapporte au Director ce qui a été créé, ce qui existait déjà (jamais modifié), et le résultat de la vérification.
4. Si `AGENTS.md` existait déjà, propose d'y ajouter la consigne de charger les règles communes (voir le modèle dans `scripts/init_project.py`) sans l'écraser.

Ce skill ne gère que le **mono-repo** : pour un projet multi-repos, ajoute ensuite à la main une section `[repos.<nom>]` par repo (`path`, `proof`, `needs`) dans `.ballet/config.toml`, puis vérifie :

```sh
python3 <chemin>/scripts/ballet_config.py check .
```

Tu ne modifies que ces fichiers, et rien d'autre dans le projet.
