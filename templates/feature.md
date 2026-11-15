# FEAT-NNN — Nom de la feature

- **Statut** : draft | ready
- **Capability** : CAP-NNN
- **Répond à** : OPP-NNN (facultatif)
- **Dépend de** : FEAT-NNN (facultatif)

## Problème

Pour qui, et ce que ça coûte aujourd'hui. Une ou deux phrases reprises de l'opportunité ou de la capability.

## Proposition

Ce que le produit saura faire, à gros grain. Une feature `draft` peut s'arrêter ici.

## Parcours

Ce que la personne voit et fait, étape par étape, en langage métier : état vide, chargement, erreur. Absent si la feature n'a pas d'écran.

## Règles

Invariants, refus et cas limites tranchés pendant le Workshop.

## Critères d'acceptation

Quatre au plus : au-delà, la feature est trop grosse et se recoupe. Des scénarios vérifiables, tagués `@FEAT-NNN-C1` : le même tag se retrouve sur les tests qui les couvrent. On ne renumérote jamais, on ajoute à la fin. L'avancement ne s'écrit pas ici.

```gherkin
@FEAT-NNN-C1
Scenario: alice …
  Given …
  When …
  Then …
```

## Hors périmètre

Obligatoire : ce que la feature ne fait pas, et où c'est traité le cas échéant.

## Questions ouvertes

- [ ] …
