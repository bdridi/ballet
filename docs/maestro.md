# Maestro, the Monitor and the machine

Reference for everything that runs across your projects. The short version is in the [README](../README.md).

Ballet's state lives on your machine, never in your projects. Maestro and the Monitor are the two long-running parts; Conductors come and go.

| Who | What it is | Does |
|---|---|---|
| **Maestro** | one Claude session, always open (`/ballet:maestro`) | tells you what needs a decision, carries your answers, launches Conductors |
| **Monitor** | a script with no LLM (`ballet_monitor.py`) | watches GitHub and the Conductors, writes facts into Maestro's mailbox |
| **Conductor** | one session per item (`/ballet:rehearsal`) | plays the item's Rehearsals up to its last Premiere |

The Monitor only states facts: it launches nothing, closes nothing and never talks to you.

## Set up the machine: `/ballet:setup`

Run it once, on your own machine, with the Orca app open. Every step can be rerun.

1. Checks the tools (`git`, `python3`, `gh`, `claude`, `orca`).
2. Reinstalls the plugin from its clone.
3. Registers your projects (an alias and a path each) in `~/.ballet/maestro.toml` and in Orca.
4. Offers `/ballet:init-project` to the projects without a profile.
5. Creates **Maestro's mailbox** (`ballet_maestro.py mailbox`): an empty Orca terminal and its Run. Every Conductor posts a message there when it escalates or finishes (`antimurphy#12 · escalate`).
6. Starts the **Monitor** in its own Orca terminal, `ballet-monitor`.
7. Starts **Maestro** in an Orca terminal titled `maestro`: it runs `claude --remote-control 'ballet maestro' '/ballet:maestro'`, so you can reach it from the Claude app (Mac or phone) as « ballet maestro ». Keep that tab open.
8. Imports the state of older versions, once (see [The state](#the-state)).

## Upgrade: `/ballet:setup upgrade`

After a `git pull` in the clone. Run it from any session but Maestro's. It stops the Monitor and Maestro, reinstalls the plugin, imports an older state, then starts a new Monitor and a new Maestro, which reads what came in meanwhile. Running Conductors are left alone.

The Stage shows the installed version and the versions Maestro and the Monitor run (each notes its own when it starts). When they differ it says `Monitor 0.45.0, installed 0.47.0 : run /ballet:setup upgrade`.

## Maestro

### Starting

Maestro takes the **lease** on the mailbox (`ballet_maestro.py claim`). Only one session may read it, because reading consumes the messages. `claim --take-over` replaces a dead or cleared session; only on your yes.

It then tells you *While you were away: …*, and sleeps on the mailbox (`wait`, in the background). It wakes at each message to tell you why, with the links and what to decide.

### Push to your phone

At each escalation and each question, Maestro also pushes one line to your phone (the `PushNotification` tool). Setting: `[maestro] push` in `~/.ballet/maestro.toml`, on by default. It needs:

- Remote Control (Maestro's session has it);
- the Claude mobile app signed in to the same account;
- Claude Code's `agentPushNotifEnabled` setting (`/config`).

Claude Code skips the push while the terminal is in use, and a failed push never blocks Maestro.

### What you can ask Maestro

Maestro runs these scripts (in `scripts/`) for you; you can also run them yourself.

| Command | Does |
|---|---|
| `ballet_maestro.py status` | each project's open sessions, and the Conductors Maestro launched, with the state of their terminals |
| `ballet_maestro.py ready` | the ready items no Conductor plays yet, in queue order |
| `ballet_maestro.py tell <project>#<item> <answer>` | carries your answer to that Conductor's terminal |
| `ballet_maestro.py tell --override <project>#<item> <reason>` | your reason to force what blocks it (a failure, a policy refusal, a size, a turn limit) |
| `ballet_maestro.py pause` / `resume` | nothing leaves on its own while paused |
| `ballet_launch.py rehearsal <project> <item>` | starts a Conductor on your word |
| `ballet_launch.py workshop <project> [<item>]` | starts an autopilot Workshop |
| `ballet_launch.py stop <project>#<item>` | stops a working Conductor and keeps its work |
| `ballet_launch.py close <project>#<item>` | closes the terminal of a Conductor that finished |
| `ballet_restart.py when-idle` | clears Maestro's own context (see below) |

### Launching a Conductor

`ballet_launch.py` opens an Orca terminal in the project and runs `claude --remote-control '<project>#<item>' '/ballet:rehearsal #<n>'` there. You can open that session from your phone: Maestro gives you its Remote Control URL when it is found.

Four guards come first:

1. a known project;
2. no Conductor already alive on the item;
3. at most `max_running` Conductors alive (3) and `max_per_day` launches a day (10), both in `[limits]` of `~/.ballet/maestro.toml`;
4. at most `max_running` under `[projects.<alias>]` for that project, when set.

Rehearsals of one project can run side by side: the script runs their proofs one at a time (a lock per project), so two proofs never fight over a port.

**Dependencies.** Between items they are GitHub's native "Blocked by" links, which the Dramaturg sets when it publishes an issue (a `Depends on: FEAT-002` line in the specs). An item starts only when all its blockers are closed; `ballet_launch.py` refuses a blocked item (`--ignore-blockers`, on your explicit word only).

**What Maestro does with a `ready` item** is a rule a script computes. `auto_launch = ["Task", "Bug"]` under `[projects.<alias>]` lists the types launched on their own (empty by default: Maestro always asks you). `wait` and `recap` write one of these under each ready item:

- `DECISION: launch`
- `DECISION: wait (blocked by #M, open)`
- `DECISION: ask the Director (<reason>)`

A launch refused by a limit stays in `ready` until a `done` or a `gone` frees a slot.

### Stopping a Conductor

`stop` closes its terminal and stops its Orca workers. Its Rehearsal (or Workshop) and the issue's Ballet status become `escalated`; state, branch, worktree and pull request stay. It frees a slot (`stopped` in the registry) and is never relaunched on its own. Resuming it mid-flight is still to come (OPP-80).

### Clearing Maestro's context: `restart`

`ballet_restart.py when-idle`:

1. pauses auto launch;
2. waits until no Conductor is working (one paused on an escalation does not count) and Maestro sleeps on its mailbox;
3. replaces the session in its Orca tab with a fresh one, which takes the lease and opens with *While you were away*;
4. lifts the pause.

It gives up after four hours (`maestro · restart abandoned` in the mailbox). Maestro does it on its own when the Monitor reports its context over the threshold (`DECISION: restart`), and still only once no Conductor is working.

## The Monitor

Every 3 minutes it reads each project's GitHub queue and the Conductors' terminals. It writes into the mailbox:

| Message | When | Maestro's answer |
|---|---|---|
| `antimurphy#12 · ready` | an item turned `ready` (with its type, title, priority and link). The items already ready when it first looks at a project come in one message | launches or asks you (see above) |
| `antimurphy#12 · gone` (high priority) | a Conductor's terminal vanished; its registry line becomes `gone` | tells you |
| `antimurphy#12 · finished` | a Conductor Maestro launched finished but is still open after `close_finished_after_minutes` (10 by default, 0 never) | `DECISION: close` |
| `antimurphy#12 · idle` | a Conductor's Rehearsal (or Workshop) had no event and no commit in its worktree for `idle_after_minutes` (20 by default, 0 never), while no proof, mutation or wait for you runs | `DECISION: nudge` (reminds the awaited worker); a second notice an interval later comes to you |
| `maestro · context over threshold` | Maestro's transcript reaches `restart_at_context_percent` of `context_window_tokens` (30 and 1000000 by default, 0 never), once per session | `DECISION: restart` |
| `capacity · five_hour · above threshold` / `below threshold` | see below | see below |

`close_finished_after_minutes` and `idle_after_minutes` are under `[conductors]`, the context keys under `[maestro]`, all in `~/.ballet/maestro.toml`.

An item is launchable when it is `ready` with no open blocker: the Monitor wakes Maestro only then.

### Claude's capacity

Maestro and the Conductors run with Ballet's statusline (`ballet_statusline.py`, plugged by `--settings`; it runs the statusline you already have, Orca's included, after it). It is the one place where Claude Code tells how much of its 5-hour and 7-day windows is used. The figure is noted in `~/.ballet/capacity/claude.json` (read by `ballet_capacity.py`). With an API key, Bedrock or Vertex the figure is `null`: there is no probe and nothing changes.

Each turn the Monitor compares it with `[capacity]` (the plugin's `config.toml`, overridden key by key in `~/.ballet/maestro.toml`):

| Key | Default | Meaning |
|---|---|---|
| `five_hour_threshold` | 90 | percentage USED; 0 turns this window's probe off |
| `seven_day_threshold` | 90 | same, for the 7-day window |
| `stale_after_minutes` | 30 | an older figure is unknown; Ballet never holds anything on an old figure |

When a window crosses its threshold the Monitor writes `capacity · <window> · above threshold`; when it is back 5 points under (or its figure became unknown), `below threshold`. Once each way, with the window, the percentage, the threshold and the reset time.

- Above the **5-hour** threshold, Maestro launches nothing new (`DECISION: standby`): what already runs keeps running, and launching resumes on its own once it is back under.
- Above the **7-day** threshold, Maestro asks you (`DECISION: ask the Director`).
- A launch you ask for yourself is never held.

The statusline only runs in a session that displays, so a figure can be a few minutes old.

## Conductor and Maestro sessions

They start lean (`ballet_session.py`): no MCP server, only the built-in tools of their role (`Skill` stays, so the Ballet skills load), and a one-hour prompt cache (`CLAUDE_CODE_PROMPT_CACHE_TTL=1h`).

| Session | Model, first match wins |
|---|---|
| Conductor | `[conductor] model` of the project's profile, then `[conductors] model` of `~/.ballet/maestro.toml` (whole machine), then `haiku` |
| Maestro | `[maestro] model` of `~/.ballet/maestro.toml` (`sonnet` by default) |

The model is read when the session is created: a change applies at the next `/ballet:setup upgrade` (or `restart`).

Workers started by `orca orchestration worker-start` cannot be given options or variables per launch (only `--model` and `--effort`): set them once in Orca's agent settings for `claude` (default arguments and environment).

`BALLET_CONDUCTOR_COMMAND` replaces `claude`, to try a launch without tokens.

## The state

One SQLite base for the whole machine: `~/.ballet/ballet.db`. It holds:

- the registry of Conductors (project, item, kind, terminal, URL, start, last event, `running` or `finished`);
- Maestro's mailbox, lease and pause;
- the queue the Monitor saw;
- the Rehearsals, sessions and Workshops of every project;
- a journal, one shape for everything: **nodes** (a step that starts and ends: a Conductor, a Rehearsal, a role's turn, the proof, a mutation, a wait for you, played by an agent, a script or you) and their **events** (start, end, or a mark in between, such as the exchanges between roles and sessions). A node with no end is running.

Nothing is written in your projects. Working files (workers' missions, mutation logs) go to `~/.ballet/projects/<alias>/`. The TOML files (`~/.ballet/maestro.toml`, each project's `.ballet/config.toml`) stay the config, which you edit.

The base migrates itself when the plugin moves on (numbered migrations, a copy kept before each one).

The state of older versions (`conductors.json`, `monitor.json`, the state tables of `maestro.toml`, each project's `.ballet/run/`) is taken over once by `python3 <path-to-ballet>/scripts/ballet_legacy.py import` (`/ballet:setup` runs it). Until then, Maestro, the Monitor and the Conductors refuse to run.

## Still to come

- Headless mode: Maestro on a VPS (OPP-74).
- Resuming a stopped Conductor mid-flight (OPP-80).

The full list is in [`opportunities.md`](../opportunities.md).
