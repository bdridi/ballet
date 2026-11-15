# Backlog

Ce qui attend d'être fait, une ligne par entrée. Le Dramaturg le tient : il capture, classe, fusionne et arbitre. Aucun avancement ici : une entrée quitte son tableau pour *Traités* dès qu'une capability, une feature ou un brouillon d'issue y répond.

## Prochainement

Ce que le Dramaturg recommande de faire ensuite, dans l'ordre : 5 entrées au plus (`OPP-`, `BUG-`, `TASK-`, `CAP-` ou `FEAT-`), chacune avec sa raison en une ligne.

1. …

## Opportunités

Un problème pour quelqu'un, jamais une solution. Une piste peut figurer dans la preuve, après « Piste évoquée ».

| ID | Pour qui | Problème | Preuve |
| --- | --- | --- | --- |

## Retours

Les retours d'un test, notés tels quels en attendant d'être classés : **écart** (la spec le demande, le produit ne le fait pas) → bug ; **rectification** (le produit suit la spec, c'est elle qui est à revoir) → la feature est révisée ; **besoin nouveau** → opportunité.

| ID | Date, contexte | Ce qui a été vu |
| --- | --- | --- |

## Bugs

Un écart entre ce que dit la spec et ce que fait le produit. La spec ne bouge pas.

| ID | Ce que dit la spec | Ce que fait le produit | Reproduire |
| --- | --- | --- | --- |

## Tâches

Un travail sans comportement visible nouveau (outillage, dette, montée de version) : il ne passe ni par une capability ni par une feature.

| ID | Quoi | Pourquoi |
| --- | --- | --- |

## Traités

| ID | Résumé | Statut | Réponse |
| --- | --- | --- | --- |

<!-- Statut : accepted (Réponse : CAP-NNN, FEAT-NNN ou le brouillon d'issue), merged (Réponse : l'ID qui l'absorbe), rejected (Réponse : la raison). -->
