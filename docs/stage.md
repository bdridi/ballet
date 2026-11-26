# The Stage

A local, read-only page of everything Ballet plays on the machine, read from `~/.ballet/ballet.db`.

```sh
python3 <path-to-ballet>/scripts/ballet_stage.py
```

Open http://127.0.0.1:7700 (`--port` to change it). It covers every project of the machine, with a selector to keep one.

## Pages

| Page | Shows |
|---|---|
| **Dashboard** (default) | Ballet's health (Monitor, Maestro and its context, the mailbox, launches against their limits, the base, and the versions), the indicators (Premieres over 7 days, median lead time of a ticket, the Director's median response time, the share approved on the first round, agent hours), the activity heatmap, where the time goes per ticket (agent, script, Director), Rehearsal durations over time, diff sizes against their limit, the roles and the last escalations |
| **On stage** | what plays now, what waits for you first; cards up to four, a list beyond (or on demand) |
| **Program** | the queue as the Monitor last saw it, and the issues a Workshop published `proposed` (open them on GitHub to accept them: the Stage changes nothing) |
| **Workshops**, **Rehearsals** (one line per Conductor session), **Tickets** (slices included, with their cost), **Premieres** | the history |
| **Frictions** | every Rehearsal and Workshop with its frictions and its cost, and the cost of all of them per session (Dancer, Critic, Choreographer, Conductor…) |

## One Rehearsal or Workshop

- its duration in large (a live timer while it plays);
- its cost per session, in tokens and in API-equivalent dollars (read from Claude Code's journals by `ballet_cost.py`, in the background);
- its frictions and the script's closing report;
- its transitions (a flowchart of the steps, each passage counted; the proof, the mutation and the policy have their own icon);
- its communication (who talks to whom, in order) and the whole thread: click a step of the script to see its data, and the output of a mutation.

A ticket shows its total duration and its total cost.

## Good to know

- Light, dark or the system's theme; every table is paged.
- Issue titles come from `gh`, read in the background.
- It listens on 127.0.0.1 only and loads nothing from the network (Mermaid and Font Awesome are in `stage/vendor/`).
