---
name: setup
description: Sets up a machine for Ballet, once (installer): checks the tools (git, python3, gh, claude, orca), reinstalls the plugin from its clone, registers the Director's projects for Maestro (`~/.ballet/maestro.toml`) and in Orca, offers `/ballet:init-project` to the projects that lack a profile, creates Maestro's mailbox and the Monitor's terminal, and starts the Maestro session itself in its own terminal. Attended mode only for now (the Director's own machine, Orca desktop open). Use once per machine, or again to add a project or recreate a lost mailbox: every step is safe to rerun. With `upgrade` (`/ballet:setup upgrade`): applies a new version of Ballet in one go (stops the Monitor and Maestro, reinstalls the plugin, takes over an older state, starts a new Monitor and Maestro).
---

# setup

You prepare the Director's machine for Ballet, in **attended** mode: their own machine, with the Orca desktop app open. Every step below can be rerun; none creates a thing twice. The scripts are at `../../scripts/` relative to this skill's folder (`<path>` below).

## Upgrade (`/ballet:setup upgrade`)

When the argument is `upgrade`, the machine is already set up and the Director wants the new version of Ballet that is in their clone (after a `git pull`). Do only this, never the steps below. Ask where the clone is, unless `<path>` is itself a clone (it has a `.git`), then run the clone's script:

```sh
python3 <clone>/scripts/ballet_upgrade.py
```

One line per step, ✓ or ✗: the Monitor and Maestro stopped (their Orca terminals closed), the plugin reinstalled, an older state taken over into `~/.ballet/ballet.db`, the lease released, the mailbox checked, a new Monitor and a new Maestro started in their terminals. Report them. The Conductors that are running are not touched (each of their calls runs the reinstalled scripts). The new Maestro takes the lease and opens with *While you were away*: nothing in the mailbox is lost. If it refuses because it runs in Maestro's own terminal, tell the Director to run `/ballet:setup upgrade` from another session. On a ✗, give its message as is; rerunning the upgrade is safe. This session keeps the plugin it loaded: tell the Director to open a new one for anything else.

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

Ballet's state lives in one base for the whole machine, `~/.ballet/ballet.db` (the first script creates it; the TOML files stay the config). The state of an older Ballet is taken over once, by its own command, before anything else (Maestro, the Monitor, the launches and the Conductors refuse to run while it waits):

```sh
python3 <clone>/scripts/ballet_legacy.py import
```

It takes over `~/.ballet` (`conductors.json`, `monitor.json`, the state tables of `maestro.toml`) and the `.ballet/run/` of each project of `maestro.toml`; for a project with a `.ballet/run/` that is not registered, add its home at the end of the command. Each file taken over is set aside as `*.imported`; `nothing to take over` on a new machine. Report its lines. On a machine where the Monitor and Maestro already run, prefer `/ballet:setup upgrade`: it does this and restarts them.

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

## 5. The Monitor

```sh
python3 <path>/scripts/ballet_maestro.py monitor
```

It prints `monitor created: terminal <handle>` or `monitor already there: …`. The Monitor is a script, no LLM: an Orca terminal titled `ballet-monitor` runs `ballet_monitor.py run`, which every 3 minutes reads each project's GitHub queue and the Conductors' terminals, and writes into the mailbox an item that turned `ready` or a Conductor that is `gone`, and tells Maestro when its own context passes a threshold. It only states facts and launches nothing. Tell the Director not to close that terminal; if they do, rerun this step. It reports into the mailbox of step 4, so run this step after it.

Which items Maestro launches by itself is the Director's choice, per project, in `~/.ballet/maestro.toml`: `auto_launch = ["Task", "Bug"]` under `[projects.<alias>]` (nothing by default: Maestro asks every time). Offer to set it; edit the file only for a project and types the Director names, and only that line.

A Conductor that finished stays open in its terminal until Maestro closes it: the Monitor reports it after `close_finished_after_minutes` under `[conductors]` in `~/.ballet/maestro.toml` (10 by default; 0 never closes one). Mention it; change it only on the Director's word.

The models: Ballet installs with Maestro on `sonnet` and the Conductors on `haiku`; both stay Claude Code, only the model changes. A project's Conductors take `[conductor] model` of its profile, else `[conductors] model` of `~/.ballet/maestro.toml` for the whole machine, else `haiku`; Maestro takes `[maestro] model` of `~/.ballet/maestro.toml`, read when its session is created: a change applies at the next `/ballet:setup upgrade` (or `restart`). Mention it; change it only on the Director's word.

Claude's capacity is watched too (OPP-88): the Maestro and Conductor sessions run with Ballet's statusline (`ballet_statusline.py`, plugged in by `--settings`; it runs the statusline the Director already has, Orca's included, so nothing of it is lost), which notes in `~/.ballet/capacity/claude.json` how much of the 5-hour and 7-day windows is used. The Monitor compares it with `[capacity]` (the plugin's `config.toml`, overridden key by key in `~/.ballet/maestro.toml`): `five_hour_threshold` and `seven_day_threshold`, percentages USED, 90 by default (0 turns that window's probe off), and `stale_after_minutes`, 30 (an older figure is unknown: nothing is ever held on an old figure). Above the 5-hour threshold Maestro launches nothing new (`DECISION: standby`) until it is back under; above the 7-day one it asks the Director. With an API key, Bedrock or Vertex Claude Code sends no `rate_limits`: there is no probe and nothing changes. Mention it; change a key only on the Director's word.

Maestro's own context is watched too: when it passes `restart_at_context_percent` under `[maestro]` in the same file (30 by default, of `context_window_tokens`, 1000000 by default; 0 never), the Monitor says so once and Maestro restarts itself, but only once no Conductor is working (`ballet_restart.py when-idle`). Mention it; change either key only on the Director's word.

## 6. Maestro itself

```sh
python3 <path>/scripts/ballet_maestro.py maestro
```

It prints `maestro created: terminal <handle>` or `maestro already there: …`. An Orca terminal titled `maestro` runs `claude --remote-control 'ballet maestro' '/ballet:maestro'` with a lean base (no MCP server, only the tools it needs, a one-hour prompt cache): a real Claude session, which takes the lease on the mailbox and sleeps on it, reachable from the Claude app (Mac or phone) under the name **ballet maestro** (Remote Control). Run this step after the mailbox and the Monitor. It creates nothing when its terminal is alive, **and nothing either when a Maestro session already holds a live lease** (it says so: two sessions would fight over the mailbox). Relay that message; never `claim --take-over` yourself, that is the Director's yes to give. Run it only on a machine where `claude` is installed and logged in (step 1 checked it).

## 7. Report

Sum up in a few lines: the tools, the plugin, the projects (registered, in Orca, with or without a profile), the mailbox, the Monitor, Maestro. Then tell the Director where Maestro is: **it runs in the Orca tab `maestro`, and it is reachable in the Claude app under the name « ballet maestro »** (Remote Control, on the Mac as on a phone). It took the lease, tells what happened while they were away, then sleeps on the mailbox and wakes at each escalation. **They must not close that tab.** Opening `/ballet:maestro` somewhere else runs into the lease, and `--take-over` is only for when they say yes (the session in the tab then stops being Maestro). If step 6 said a session already held the lease, report that instead: no second Maestro was started. Then say plainly what is **not there yet**:

- a Monitor that spots a Conductor that is frozen (its terminal alive, nothing said): it only sees a vanished one;
- the headless mode (a VPS, `orca serve` under systemd, the keeper).

You change nothing in the projects (the import only sets an old `.ballet/run/` aside as `.ballet/run.imported`): only `~/.ballet/`, Orca's project list, and the mailbox, Monitor and Maestro terminals.
