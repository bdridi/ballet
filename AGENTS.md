# Ballet — règles du repo

Ce repo est la source du plugin Ballet. La méthode est décrite dans `PRD.md`, le plan d'implémentation dans `TASKS.md`.

## Vocabulaire

Un seul nom par concept, celui de la section 3 du PRD, partout : doc, skills, clés de config, commandes (Dramaturg, Choreographer, Dancer, Critic, Conductor, Director, Workshop, Rehearsal, Premiere, Piece). L'équivalent fonctionnel (PM, architecte, dev, validateur) n'apparaît que dans la description d'un skill.

## Scripts

- Python, dernière version, bibliothèque standard uniquement.
- Un script a un seul objectif (config, politique, GitHub…).
- Une fonction publique se lit comme une histoire : une suite d'étapes nommées, à un niveau d'abstraction élevé.
- Un seul niveau d'abstraction par fonction ; les détails techniques descendent dans des fonctions privées bien nommées.
- Pas de code « ultra technique » : la lisibilité prime sur l'astuce.
- Les messages affichés (erreurs, refus, rapports, aide) sont en anglais : les agents les lisent. Docstrings, commentaires et noms de tests restent en français.
