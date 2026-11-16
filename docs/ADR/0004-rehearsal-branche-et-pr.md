# ADR 0004 — Chaque Rehearsal sur sa branche, intégrée par une PR

- Statut : acceptée
- Date : 2026-11-16
- Source : premier run du Dancer sur antimurphy (issue #2). Le Choreographer a commité un ADR et `AGENTS.md` sur `main`, dans l'arbre où le Dancer avait des changements non commités (`pnpm-lock.yaml`) : son commit a failli les embarquer.

## Contexte

Le séquentiel faisait travailler tous les rôles sur `main`, dans le même dossier. Rien n'empêchait deux passages de se chevaucher (PRD §13 : « deux workers ne tournent jamais en même temps sur le même worktree »), et `main` recevait du code avant tout verdict.

## Décision

- **Une Rehearsal = un worktree et une branche courte**, créés par le Conductor depuis `main` : `rehearsal/<ID>` (`FEAT-NNN`, `FEAT-NNN.K`, `BUG-NNN`, `TASK-NNN`). Séquentiel ou parallèle, c'est le même mécanisme ; seul le nombre de Rehearsals ouvertes change.
- **Le Choreographer** commite ses ADR et ses règles `AGENTS.md` sur la branche de la Rehearsal, y compris quand il répond à une question du Dancer (le Dancer attend : jamais deux passages en même temps). Rien ne part directement sur `main` : une session peut écrire plusieurs ADR, ou corriger plusieurs fois le même, et tout voyage dans la PR avec le code qui le suit. Un ADR n'est acceptée qu'au merge de sa PR ; avant, il se corrige par de nouveaux commits, après, une nouvelle ADR le remplace. Ses spikes restent sur `spike/NN-slug`, jamais mergées.
- **Le Dancer** commite sur la branche qu'on lui donne. Il ne crée ni branche ni tag, ne pousse pas.
- **Le Conductor** pousse la branche, ouvre la PR (liée à l'issue), publie le verdict du Critic en une seule review, et merge (la Premiere) : verdict `APPROVED`, politique verte, CI verte, tampon de la phase. Puis il supprime la branche et le worktree.
- **Le Critic** relit dans le worktree, en lecture seule, et rend son verdict et toutes ses remarques **en un seul lot**. Il ne merge pas : juger et intégrer restent séparés.
- **Sur un `REJECTED`**, le Dancer est relancé et lit la review de la PR par le script, en lecture seule.
- **Merge par rebase** : un commit par tâche reste visible sur `main`. Pas de squash.
- **La trace** : l'issue porte le plan, ses amendements et les échanges entre rôles (questions, réponses) ; la PR porte le code, les rapports du Dancer et les verdicts du Critic. Tout reste sur GitHub, pour l'analyse.
- **Attribution des commits par passage** : la politique prend l'état avant et après chaque passage ; un commit appartient au rôle pendant le passage duquel il est apparu.
- La clé `[project] merge` (`trunk` ou `pr`) disparaît : Ballet intègre toujours par PR, sur des branches qui vivent le temps d'une Rehearsal.

## Conséquences

- `ballet_github.py` gagne : pousser une branche, ouvrir une PR, lire une PR et ses reviews, publier une review, commenter l'issue, merger par rebase, supprimer la branche mergée. Plus de push direct sur `main`.
- Le dépôt GitHub ne permet pas d'approuver sa propre PR : la review du Critic est publiée comme commentaire de review, dont la première ligne porte le verdict. Le tampon qui fait foi reste le verdict lu par le Conductor.
- Le parallèle (plus tard) ne change que la file de merge : voir PRD §7.
