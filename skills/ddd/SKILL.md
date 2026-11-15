---
name: ddd
description: Règle commune DDD. À charger pour nommer et structurer le code selon le domaine métier (langage commun, invariants, limites de contexte).
---

# DDD

- Utilise le langage du domaine dans les specs, les tests et le code. Le glossaire du projet fait foi.
- **Langue.** Specs, critères et produit dans la langue du produit ; code en anglais. Le glossaire de l'espace specs est l'unique table de correspondance : un terme y entre avec son nom métier et son nom de code en même temps, et le code n'emploie aucun nom de domaine qui n'y figure pas. Un renommage se fait d'abord dans le glossaire, puis dans le code.
- Les scénarios Gherkin restent dans la langue du produit : un critère se vérifie en regardant le produit, qui affiche ses textes dans sa langue. Le lien entre un critère et son test passe par le tag (`@FEAT-NNN-Cn`), jamais par le texte du scénario : on ne traduit aucune phrase Gherkin dans le code.
- Les invariants du domaine vivent dans le modèle, pas dans les couches techniques.
- Une notion métier a un seul nom et un seul endroit où elle est définie.
- Respecte les limites de contexte : pas de fuite d'un modèle dans un autre.
