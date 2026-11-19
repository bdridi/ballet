# Ballet — règles du repo

Ce repo est la source du plugin Ballet. La méthode est décrite dans `PRD.md`, ce qui reste à faire dans `opportunities.md`, ce qui est livré dans `release.md`.

## Vocabulaire

Un seul nom par concept, celui de la section 3 du PRD, partout : doc, skills, clés de config, commandes (Dramaturg, Choreographer, Dancer, Critic, Conductor, Director, Workshop, Rehearsal, Premiere, Piece). L'équivalent fonctionnel (PM, architecte, dev, validateur) n'apparaît que dans la description d'un skill.

## Scripts

- Python, dernière version, bibliothèque standard uniquement.
- Un script a un seul objectif (config, politique, GitHub…).
- Une fonction publique se lit comme une histoire : une suite d'étapes nommées, à un niveau d'abstraction élevé.
- Un seul niveau d'abstraction par fonction ; les détails techniques descendent dans des fonctions privées bien nommées.
- Pas de code « ultra technique » : la lisibilité prime sur l'astuce.
- Les messages affichés (erreurs, refus, rapports, aide) sont en anglais : les agents les lisent. Docstrings, commentaires et noms de tests restent en français.

## Versions

- Chaque version du plugin (`.claude-plugin/plugin.json`) a son entrée en tête de `release.md` : une ligne par fonctionnalité ou changement, et les opportunités qu'elle traite (`OPP-NN`).
- Une opportunité traitée passe de 🆕 à ✅ dans `opportunities.md`, avec sa version ; un nouveau sujet y entre en 🆕, avec le numéro suivant.
- La version est commitée puis taguée `vX.Y.Z`.
