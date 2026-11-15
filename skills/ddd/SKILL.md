---
name: ddd
description: Règle commune DDD. À charger pour nommer et structurer le code selon le domaine métier (langage commun, invariants, limites de contexte).
---

# DDD

- Utilise le langage du domaine, le même dans les specs, les tests et le code. Le glossaire du projet fait foi.
- Les invariants du domaine vivent dans le modèle, pas dans les couches techniques.
- Une notion métier a un seul nom et un seul endroit où elle est définie.
- Respecte les limites de contexte : pas de fuite d'un modèle dans un autre.
