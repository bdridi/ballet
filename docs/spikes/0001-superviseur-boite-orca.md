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
5. **Orca sans fenêtre : vérifié sous `orcad` sur le Mac (essai 2), reste Linux.** `orca serve` refuse de
   démarrer (code 3) tant que l'application de bureau sert le profil : il faut la fermer.

## Essai 2 — Orca sans fenêtre, sous `orcad` (Mac, application de bureau fermée)

`ORCA_SERVE_RUNTIME=orcad orca serve --no-pairing --bind 127.0.0.1` : le runtime Node, celui de Linux par défaut.

| Essai | Résultat |
|---|---|
| fermer l'application de bureau | le démon des terminaux d'Orca reste vivant, et ses terminaux aussi (le Claude du Conductor de #55 tournait encore) |
| `orca serve` sous `orcad` | `Orca server ready`, `ws://127.0.0.1:6768`, PTY testé ; « terminals survive an orcad restart: yes » ; la CLI le joint en quelques secondes |
| projets et worktrees | les mêmes que ceux de l'application (8 projets, 11 espaces) |
| boîte du superviseur (terminal + `run-create --from`) | ok |
| `claude --remote-control "spike orcad"` dans un terminal Orca (`terminal create --command`) | ok : « /remote-control is active · Continue here, on your phone », une URL `claude.ai/code/session_…` ; `ORCA_TERMINAL_HANDLE` posé |
| ce Claude envoie `status` à la boîte | reçu ; le `check --wait` du superviseur se réveille |
| `orchestration worker-start --agent claude` (le chemin de `ballet_orca.start_worker`), le worker envoie `worker_done` | reçu ; le `check --wait --types worker_done` du coordinateur se réveille. Le worker part en mode `structured` (chat) |
| redémarrer `orca serve` | les terminaux, leurs handles, la Run et ses messages survivent ; le Claude en Remote Control écrit encore dans la boîte après le redémarrage |

Deux pièges notés : un prompt placé après `--allowedTools` est pris pour une valeur de l'option (le mettre
avant, ou après `--`) ; sans `--dangerously-skip-permissions`, `--allowedTools "Bash(orca:*)"` et le mode auto
suffisent à ce Claude pour parler à Orca.

## Ce qu'il reste à vérifier sur le VPS

- Linux et systemd : `orca serve --supervise` en service, au démarrage de la machine, sans session ouverte.
- Un vrai Conductor de bout en bout (une petite `Task`) sous `orcad`, avec le Dancer et le Critic.
- L'avertissement « Bypass Permissions » de `orca agent launch` : accepté une fois sur le VPS, ne revient-il plus ?
  Sinon, lancer les Conductors par `terminal create --command`, comme ici, avec leurs outils autorisés.
- L'accès : `--bind 127.0.0.1` et un tunnel SSH ou Tailscale pour l'application Orca du Mac, si besoin.

## Piste : chaque Conductor en Remote Control

Le Director parle au Conductor par le Supervisor (`orca terminal send` vers son terminal ; le Conductor répond
par la boîte) ; il doit aussi pouvoir lui parler en direct, depuis son téléphone, quand il le veut. **Vérifié
sous `orcad` (essai 2) :** `claude --remote-control` dans un terminal Orca s'ouvre en Remote Control et garde la
boîte et les réveils. Les points de départ :

- `claude --remote-control "<projet>#<élément>"` (l'option existe dans la CLI) : par `orca agent launch`, s'il
  transmet des options à `claude`, sinon par `orca terminal create --command "claude --remote-control … '/ballet:rehearsal #N'"`.
  Le terminal reste un terminal Orca : `ORCA_TERMINAL_HANDLE` y est posé, la boîte et les réveils marchent ?
- La session apparaît-elle dans l'application Claude, nommée par son élément ?
- Deux voix, une seule main : le Director qui répond en direct au Conductor, le Supervisor doit le savoir (il
  relit la session ou le journal avant de porter une réponse), pour ne pas répondre deux fois.

## Architecture cible (OPP-02)

Tout tourne sur une machine toujours allumée (le VPS), sous Orca sans fenêtre. Le Director ne parle qu'au
Supervisor, depuis l'application Claude (téléphone ou Mac) ; il peut aussi ouvrir un Conductor en direct.
Le nom `ballet_stage.py` est déjà pris (la Scène, tableau de bord en lecture seule) : le Supervisor garde
son nom du vocabulaire, son nom de scène reste à trouver.

```mermaid
flowchart TB
    director(["Director<br/>application Claude"])
    github[("GitHub<br/>issues, Ballet status, PR, CI")]

    subgraph vps["VPS · systemd"]
        orcad["orca serve --supervise<br/>(orcad)"]
        subgraph orca["terminaux Orca"]
            supervisor["Supervisor<br/>claude --remote-control<br/>/ballet:supervisor"]
            mailbox[["boîte du Supervisor<br/>Run run:&lt;id&gt;"]]
            daemon["démon ballet_supervisor.py<br/>sans LLM"]
            conductor["Conductor projet#élément<br/>claude --remote-control<br/>/ballet:rehearsal"]
            workers["workers Orca<br/>Choreographer · Dancer · Critic"]
        end
        state[("~/.ballet/<br/>projets, registre<br/>(SQLite plus tard)")]
    end

    director <-->|Remote Control| supervisor
    director -.->|en direct, au besoin| conductor
    daemon -->|"poll : passé ready ?"| github
    daemon -->|"status : ready, Conductor mort"| mailbox
    daemon -->|"lance (auto) ou sur le oui du Director"| conductor
    daemon --- state
    supervisor -->|"check --wait (Monitor)"| mailbox
    supervisor -->|"launch"| conductor
    supervisor -->|"tell : orca terminal send"| conductor
    supervisor --- state
    conductor -->|"status : escalate, question, done"| mailbox
    conductor <-->|"worker-start / worker_done"| workers
    conductor -->|"PR, labels, merge"| github
    orcad -.- orca
```

### Les quatre voies de communication

| De → vers | Par | Quand |
|---|---|---|
| Conductor → Supervisor | `orchestration send --to run:<id> --type status` (le script, pas le Conductor) | à chaque `NEXT: escalate` (question comprise) et `NEXT: done` |
| démon → Supervisor | la même boîte, depuis son propre terminal Orca | un élément passé `ready` ; un Conductor mort ou figé |
| Supervisor → Conductor | `orca terminal send --terminal <handle> --enter` | une réponse, une revue de plan, `approve`, `resume` ; le Conductor écrit le message Ballet et lance `receive` |
| Director ↔ Conductor | Remote Control du Conductor | au besoin ; le Supervisor relit la session avant de porter une réponse |

Entre le Conductor et ses workers, rien ne change : `worker-start`, `worker_done`, `question` et `reply`, la
boîte de la Run du Conductor.

### Une feature passe `ready`

```mermaid
sequenceDiagram
    actor D as Director
    participant GH as GitHub
    participant DM as démon
    participant B as boîte du Supervisor
    participant S as Supervisor
    participant C as Conductor

    D->>GH: Ballet status = ready (#60)
    DM->>GH: poll (2-5 min)
    DM->>B: status « antimurphy#60 · ready »
    B-->>S: check --wait se termine : réveil
    alt type confié à l'auto
        DM->>C: lance /ballet:rehearsal #60
        S->>D: « antimurphy #60 est partie en Rehearsal »
    else sinon
        S->>D: « antimurphy #60 est prête, je lance ? »
        D->>S: oui
        S->>C: launch : terminal create --command "claude --remote-control … /ballet:rehearsal #60"
    end
    S->>B: réarme check --wait
```

### Une escalade, puis la réponse

```mermaid
sequenceDiagram
    actor D as Director
    participant S as Supervisor
    participant B as boîte du Supervisor
    participant C as Conductor
    participant W as worker (Choreographer)

    W->>C: worker_done : plan écrit
    C->>C: receive → NEXT: escalate « plan to review »
    C->>B: status « antimurphy#60 · escalate » (le script)
    B-->>S: réveil
    S->>D: le motif, les liens, ce qu'il faut décider
    D->>S: « approuve le plan »
    S->>C: tell : orca terminal send « Director answers: approve »
    C->>C: écrit le message Ballet, receive → NEXT: wait
    S->>B: réarme check --wait
```

### Quand la session du Supervisor meurt ou est nettoyée

Elle ne porte rien que la boîte, l'état des projets et `~/.ballet/` ne gardent pas. Pendant son absence, les
Conductors et le démon continuent, les messages s'accumulent. Au redémarrage (ou après `/clear`),
`/ballet:supervisor` relit le non-lu **et** les derniers messages de l'historique (`orchestration inbox
--full` : un message lu juste avant la mort de la session n'est plus non lu), dit « pendant ton absence : … »,
puis réarme son `Monitor`. Si le processus meurt, le démon le voit (son handle ne répond plus) et relance le
terminal du Supervisor ; seule l'URL Remote Control change, la session garde son nom dans l'application.

## Première installation (cible)

Ce qui existe aujourd'hui est marqué ✅ ; le reste est à construire avec OPP-02.

1. **La machine** : Linux toujours allumé, un utilisateur dédié, sans droits sur autre chose que ses projets.
2. **Les outils** : `git`, Python récent, `gh` authentifié (un jeton fin, limité aux repos Ballet ; le scope
   `user` pour les champs d'issues, voir le README), Claude Code (`claude`, connecté au compte), la CLI
   Orca. ✅
3. **Orca sans fenêtre** : un service systemd qui lance `orca serve --supervise --bind 127.0.0.1` (sous
   Linux, `orcad` par défaut). Pour l'application Orca du Mac, un tunnel SSH ou Tailscale. ✅ (vérifié sous
   `orcad` sur le Mac ; systemd reste à essayer)
4. **Ballet** : cloner ce repo, puis `python3 <ballet>/scripts/reset_plugin.py` (installe le plugin pour
   les CLI présentes). ✅
5. **Chaque projet** : le cloner, l'ajouter à Orca (`orca repo add --path <projet>`), puis une fois
   `/ballet:init-project` dans le projet (profil, AGENTS.md, types et champs GitHub). ✅
6. **Le Supervisor** : `~/.ballet/supervisor.toml` (les projets connus, leur alias et leur chemin, les
   types en `auto_launch`, les plafonds), puis `python3 <ballet>/scripts/ballet_supervisor.py setup` :
   crée le terminal de la boîte et sa Run, lance le démon dans son terminal Orca, puis la session du
   Supervisor (`claude --remote-control "ballet supervisor" "/ballet:supervisor"`). *À construire.*
7. **Une fois sur la machine** : ouvrir chaque CLI une première fois (connexion, confiance dans les
   dossiers), et accepter l'avertissement « Bypass Permissions » si les Conductors sont lancés ainsi
   (sinon, leurs outils autorisés, comme au spike).
8. **Vérifier** : dans l'application Claude, la session « ballet supervisor » répond à `status` ; un
   élément passé `ready` sur un projet de test réveille le Supervisor.
