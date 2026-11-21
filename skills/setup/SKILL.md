---
name: setup
description: Sets up a machine for Ballet, once (installer): checks the tools (git, python3, gh, claude, orca), reinstalls the plugin from its clone, registers the Director's projects for Maestro (`~/.ballet/maestro.toml`) and in Orca, offers `/ballet:init-project` to the projects that lack a profile, and creates Maestro's mailbox. Attended mode only for now (the Director's own machine, Orca desktop open). Use once per machine, or again to add a project or recreate a lost mailbox: every step is safe to rerun.
---

# setup

You prepare the Director's machine for Ballet, in **attended** mode: their own machine, with the Orca desktop app open. Every step below can be rerun; none creates a thing twice. The scripts are at `../../scripts/` relative to this skill's folder (`<path>` below).

## 1. The tools

Run each check and report one line per tool, ✓ or ✗ with what to do:

```sh
git --version
python3 --version
gh auth status
claude --version
orca status --json
```

- `python3` must be 3.11 or later (the scripts read TOML).
- `gh auth status` must show a logged-in account with the `repo` scope, plus `user` for a personal account (the issue fields, see the README). A missing scope is fixed by `gh auth refresh -h github.com -s user`, which only the Director can run (it opens a browser): give them the command, never run it with other credentials.
- `orca status --json` must say Orca is reachable. If not, ask the Director to open the Orca app, then check again. Never run `orca open` yourself.

Stop at the first ✗ that blocks the rest (`python3`, `orca`); a missing `gh` scope blocks only the GitHub step of `init-project`.

## 2. The plugin

Ask the Director where their Ballet clone is, unless `<path>` is itself a clone (it has a `.git`). Then run the clone's script, never the one of an installed copy:

```sh
python3 <clone>/scripts/reset_plugin.py
```

Report each line. The open sessions keep the plugin they loaded: this one included, which is fine for the rest of the setup.

## 3. The projects

Ask the Director for each project: a short alias (lowercase, e.g. `antimurphy`) and its home folder (the repo, or the specs repo of a multi-repo project). For each one:

```sh
python3 <path>/scripts/ballet_maestro.py project add <alias> <home>
orca repo add --path <home> --json
```

`orca repo add` on a project Orca already knows is fine: say it is already there. Then list what Maestro knows:

```sh
python3 <path>/scripts/ballet_maestro.py project list
```

For each project whose home has no `.ballet/config.toml`, offer `/ballet:init-project`, to run from that project's home (a session opened there). Do not run it from here: it writes into the project.

## 4. Maestro's mailbox

```sh
python3 <path>/scripts/ballet_maestro.py mailbox
```

It prints `mailbox created: terminal <handle>, run:<id>` or `mailbox already there: …`. There is only ever one mailbox: the script does nothing while the terminal it noted is alive, and refuses (exit 1) when Orca does not answer. The mailbox terminal is an empty shell titled `maestro-mailbox`: tell the Director never to type in it or close it.

From now on, each Conductor (`/ballet:rehearsal`, `/ballet:workshop --autopilot`) posts a `status` message to that mailbox when it escalates or finishes, subject `<alias>#<item> · escalate` (or `· done`).

## 5. Report

Sum up in a few lines: the tools, the plugin, the projects (registered, in Orca, with or without a profile), the mailbox. Then tell the Director what to do next: **open `/ballet:maestro`** in a session of their own, from anywhere. That session takes the lease (only one session reads the mailbox), tells what happened while they were away, then sleeps on the mailbox and wakes at each escalation. Then say plainly what is **not there yet**:

- `ballet_launch.py` and the Conductors' registry: Conductors are still launched by hand, one per item;
- the Monitor (`ballet_monitor.py`), which will watch GitHub for items turned `ready`;
- the headless mode (a VPS, `orca serve` under systemd, the keeper).

You change nothing in the projects: only `~/.ballet/`, Orca's project list and its mailbox terminal.
