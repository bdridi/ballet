# Spike 0001 — Un superviseur joignable par les Conductors, et Orca sans fenêtre

Date : 2026-11-20. Branche : `spike/headless-orca`.

## Question

Le Directeur veut parler à une seule session (le superviseur, sur un VPS, en Remote Control) qui lance les
Conductors dans le bon projet, suit leur état, et apprend leurs escalades sans les lire terminal par terminal.
Deux inconnues :

1. Un processus qui n'est pas un terminal Orca (la session du superviseur) peut-il recevoir les messages des
   Conductors, et être réveillé par eux ?
2. Orca tourne-t-il sans fenêtre (`orca serve`) assez bien pour porter les Conductors et leurs workers ?

## Ce qui a été essayé (Orca local, macOS, application de bureau ouverte)

| Essai | Résultat |
|---|---|
| `ballet_rehearsal.py begin 55` depuis une session hors Orca | refusé : `no_active_sender_terminal` (toute commande `orca orchestration` veut le terminal appelant) |
| `orca orchestration run-create` depuis la même session | même refus |
| `orca terminal create --title "supervisor-mailbox"` (un shell vide, à lui seul) | ok : un handle `term_…` |
| `run-create --from <ce handle>` | ok : une Run `run_…`, sa boîte `run:<id>` |
| depuis un autre terminal Orca : `orchestration send --to run:<id> --type escalation` | refusé par Orca : `sender_not_assignee` (une escalade vient d'un worker dispatché) ; la boîte reçoit un avis de rejet |
| depuis ce terminal : `orchestration send --to run:<id> --type status --priority high` | ok : le message est dans la boîte |
| côté superviseur : `orchestration check --terminal <boîte> --run <id> --wait` lancé en arrière-plan | il se termine dès qu'un message arrive : c'est le réveil |

## Constats

1. **Le superviseur peut avoir une boîte.** Il suffit d'un terminal Orca qui n'appartient qu'à lui (un shell
   vide, jamais un autre agent), d'une Run créée `--from` ce terminal, et de lire avec `--terminal <boîte>`.
   Ce n'est pas le détournement contre lequel Orca prévient : la boîte n'est le terminal de personne d'autre.
2. **Le réveil marche.** Un `orchestration check … --wait` en arrière-plan (un `Monitor` dans Claude Code) se
   termine à l'arrivée d'un message, ce qui réveille la session du superviseur. En lecture qui consomme (sans
   `--peek`), chaque tour rend le lot suivant ; `--peek` rend toujours le plus ancien non lu, donc ne convient
   pas à une boucle.
3. **Le type compte.** `escalation`, `worker_done` et `heartbeat` sont réservés aux workers d'une Dispatch. Un
   Conductor qui prévient le superviseur envoie `status` (priorité `high`), avec un sujet stable :
   `<projet>#<item> · <NEXT>`.
4. **Qui envoie.** Le Conductor tourne dans un terminal Orca : son `ORCA_TERMINAL_HANDLE` suffit comme
   expéditeur. C'est au script de l'envoyer (`ballet_rehearsal.py`, au moment où il écrit `NEXT: escalate` ou
   `NEXT: done`), pas au Conductor : il ne fait que relayer.
5. **Orca sans fenêtre : non vérifié ici.** `orca serve` existe (« sans fenêtre de bureau »), avec `--supervise`
   pour systemd/launchd et, sous Linux, le runtime Node `orcad` par défaut. Il refuse de démarrer (code 3)
   quand une autre instance sert déjà le profil : ici l'application de bureau. Le vrai essai se fait sur le VPS.

## Ce qu'il reste à vérifier sur le VPS

- `orca serve --supervise` sous systemd, puis `orca agent launch --agent claude --surface terminal` : le
  terminal tient-il, la commande `claude` reçoit-elle son prompt ?
- Un aller-retour Conductor ↔ worker complet (`worker_done` qui réveille le Conductor) sous `orcad`.
- L'avertissement « Bypass Permissions » de Claude : accepté une fois sur le VPS, ne revient-il plus ?
- La boîte du superviseur survit-elle à un redémarrage d'`orca serve` (Run et handle) ? Les handles sont liés
  au runtime : après un redémarrage, recréer le terminal et la Run, et le noter dans le registre.

## Conséquence pour la suite

Le démon (sans LLM) et la session du superviseur peuvent se parler par la même boîte : le démon y dépose aussi
ses événements (élément passé `ready`, Conductor lancé), en `status`. Le superviseur n'a qu'une chose à
surveiller. Nom : `ballet_stage.py` est déjà pris (la Scène, tableau de bord en lecture seule) ; il faut un
autre nom pour le superviseur.
