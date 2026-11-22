# Spike 0002 — Le réveil d'Orca qui ne nomme que le Run

Date : 2026-11-22. Orca 1.4.259 (application de bureau, macOS).

## Question

Depuis le 21/11, le terminal du Conductor ne reçoit plus le message entier d'un worker, seulement :

    You have 1 orchestration message. Run `orca orchestration check --run run_da2c026b1ed3`.

Le réveil ne nomme ni `msg_…` ni `ctx_…`, et `ballet_rehearsal.py receive` n'acceptait que `--message`, `--dispatch`
ou `--mutation` (FEAT-007 #59 et FEAT-008 #60 sur antimurphy : le Conductor a contourné par `status --json` puis
`--dispatch`). Que rend `orchestration check --run`, faut-il acquitter, et que devient l'arriéré ?

## Ce qui a été essayé

| Essai | Résultat |
|---|---|
| `orca orchestration check --help` | une lecture qui consomme rend le plus ancien lot non lu du Run et le marque traité ; `--ack` ne sert qu'à un Orca plus ancien ; un script qui ne fait que regarder doit utiliser `--peek` |
| un terminal jetable, `run-create --from <terminal>`, deux `status` envoyés d'un autre terminal (`send --from`) | reçus : `messageId` rendu |
| `check --terminal <t> --run <r> --peek --json` | les deux messages, rien de marqué |
| `check --terminal <t> --run <r> --json` | les deux messages, dans l'ordre : `id`, `type`, `subject`, `from`, `payload`, `body` ; pas d'id de livraison |
| le même `check` aussitôt après | `{"messages": []}` ; `inbox` les montre `read: 1` |
| `check --run <r> --json` hors d'un terminal Orca | refusé : `no_active_sender_terminal` (il faut `ORCA_TERMINAL_HANDLE`, celui du Conductor) |
| `inbox --terminal run:run_da2c026b1ed3` (le vrai Run du Conductor de #60) | les messages traités par Ballet sont tous `read: 0` : Ballet lisait par `inbox` sans jamais consommer |

Terminaux jetables fermés (`orca terminal close`).

## Conclusion

- `receive [<ID>] --run <run>` consomme le lot par `check --run <run> --json`, depuis le terminal du Conductor ; pas
  d'acquittement.
- Le premier `check` d'un Run déjà ancien rend tout l'arriéré non lu : le script ne garde que les messages des
  workers de la Rehearsal (ou du Workshop) en cours, et le réveil de sa mutation, et ignore ceux qu'il a déjà
  traités (`received` dans l'état, rempli par les trois chemins).
- Maestro n'est pas concerné : il consomme le Run de sa propre boîte, avec son terminal ; les Runs des Conductors
  sont d'autres Runs.
