# Ballet

A common method to make coding agents (Claude, Grok, Mistral Vibe…) work as a chain, on Orca.
Ballet is a plugin: install it once, and all your projects benefit.

You frame the work with an agent. Then Ballet plans it, codes it, reviews it and merges it, one pull request at a time, and stops to ask you whenever something needs your decision.

> **Status:** under construction, used on real projects (current version in [`plugin.json`](.claude-plugin/plugin.json)). The method is in [`PRD.md`](PRD.md), what is shipped in [`release.md`](release.md), what comes next in [`opportunities.md`](opportunities.md) (all in French for now).

## How it works

You are the **Director**. Four roles do the work, each one an agent in its own session:

| Role | Does | Touches |
|---|---|---|
| **Dramaturg** | frames a need with you into a ready feature (what and why), and publishes its issue | the specs; GitHub only to publish |
| **Choreographer** | writes the technical plan on the issue, cut into slices when it is big; writes the ADRs | ADRs and `AGENTS.md` only |
| **Dancer** | codes the plan, test first, one commit per task | the code |
| **Critic** | reviews the pull request and returns a verdict | nothing (read-only) |

Around them:

- The **Conductor** runs the roles on Orca for you: it carries their questions, publishes everything on GitHub and merges once the Critic approves and the CI is green. A script checks after each role that it stayed in its perimeter; a role that oversteps is sent back once, then you decide.
- **Maestro** is the one session you talk to about all your projects. It tells you what needs a decision and launches Conductors.
- The **Monitor** (a script) watches your GitHub queue and tells Maestro when an item is ready.
- The **Stage** is a read-only web page showing everything that plays.

One issue played this way is a **Rehearsal**; its merge is the **Premiere**.

```
need ──► Workshop ──► ready issue ──► Rehearsal ──► Premiere
        (Dramaturg)                (Choreographer → Dancer ⇄ Critic)   (merged)
```

## Requirements

- macOS with Orca installed and running.
- At least one authenticated CLI: Claude Code (`claude`), Grok (`grok`) or Mistral Vibe (`vibe`).
- The GitHub CLI (`gh`), authenticated, and a GitHub remote for each project.
  - Personal repo: `gh` needs the `user` scope (`gh auth refresh -h github.com -s user`), so Ballet can create its issue types and fields.
  - Organization repo: you must be one of its owners.
- A CI on the project's pull requests that runs its proof command. Ballet never merges without a green CI (no CI counts as not green).
- Python 3.11 or later (standard library only).
- A clone of this repo, e.g. `~/Workspace/ballet`. Below, `<path-to-ballet>` is that path.

## Get started

### 1. Install the plugin (once per machine)

```sh
python3 <path-to-ballet>/scripts/reset_plugin.py
```

It installs Ballet for every CLI found on the machine:

- **Claude Code**: adds the local marketplace `ballet-local`, installs `ballet@ballet-local`, and writes the `reset-ballet` skill in `~/.claude/skills/`.
- **Mistral Vibe**: links `~/.vibe/plugins/ballet` to the clone. The first time Vibe runs in a project, accept "Trust this folder?", otherwise it loads neither `AGENTS.md` nor the project's skills.
- **Grok**: installs or updates the plugin from the clone (`--trust`: Ballet contains no hook and no MCP server).

To try Claude without installing: `claude --plugin-dir <path-to-ballet>`.

Check it worked: run `/ballet:dramaturg` in one of the CLIs. The Dramaturg should introduce itself.

### 2. Set up the machine (once)

On your own machine, with the Orca app open:

```
/ballet:setup
```

It checks the tools, registers your projects, and starts **Maestro** and the **Monitor** in their own Orca terminals. Then talk to Maestro (`/ballet:maestro`, or « ballet maestro » in the Claude app). Details: [Maestro, the Monitor and the machine](docs/maestro.md).

### 3. Bootstrap each project (once)

In the project's home folder (its repo):

```
/ballet:init-project
```

It asks for the specs space, the proof command (the one that says "it's green") and, if it is not English, the specs language. It creates:

- `.ballet/config.toml`: the project profile;
- `AGENTS.md` and `CLAUDE.md` (which imports `AGENTS.md`), without overwriting yours;
- `.claude/skills/`, and the `.agents/skills` link so that Vibe sees them;
- on GitHub, the issue type `Slice` and the issue fields Ballet's queue reads (`Ballet status`, `Rehearsal mode`, `Size`, `Plan approval`, `Priority`). Only what is missing is created. `--no-github` skips this step.

See [Configuration](docs/configuration.md) to tune the profile.

## Daily use

| You want to | Run | Then |
|---|---|---|
| frame a need, a bug, or ask "what's next?" | `/ballet:dramaturg` (or `/ballet:workshop`) | you get a ready feature, published as an issue |
| have it framed without you | `/ballet:workshop --autopilot BUG-004` | the issue waits for your yes (`proposed`), unless your profile skips it |
| play an item | `/ballet:rehearsal #12` | the Conductor plays it up to its last Premiere |
| let Ballet start the work for you | nothing: open `/ballet:maestro` | it launches what your profile allows and asks you for the rest |
| watch it play | `python3 <path-to-ballet>/scripts/ballet_stage.py` | open http://127.0.0.1:7700 |

When something needs you, the Conductor stops and tells you why and what to decide, and Maestro pushes the news to your phone. The decisions you may face (a plan to review, a question, a red proof, a policy refusal…) and your answers are in [Rehearsals and Workshops](docs/rehearsal.md).

## Go further

| Doc | About |
|---|---|
| [Rehearsals and Workshops](docs/rehearsal.md) | modes, plans, ticket sizes, autopilot, what to do when the Conductor stops |
| [Maestro, the Monitor and the machine](docs/maestro.md) | setup, launching, limits, capacity, restart, state |
| [The Stage](docs/stage.md) | what each page shows |
| [Configuration](docs/configuration.md) | the profile, mutation testing, GitHub fields, languages |
| [`PRD.md`](PRD.md) | the method, in French |
| [`release.md`](release.md), [`opportunities.md`](opportunities.md) | what is shipped, what is next |

## Known limits

- One repo per project for the Conductor (several repos come later).
- Several Rehearsals can run at once (one Conductor each, three at most by default), but one item plays its slices one after the other.
- Roles run as Orca workers with Claude Code, Codex, Grok or OpenCode. Other CLIs (Mistral Vibe…) can be used by hand, not yet by the Conductor.
- Mutation reports are read for cargo-mutants only (StrykerJS and PIT come later). Another tool still works: its exit code decides.
- Attended mode only: your own machine, Orca open. Headless is still to come.

## Update

After a `git pull` in the clone:

- run `/ballet:setup upgrade` to bring Maestro and the Monitor to the new version;
- run `/reset-ballet` in Claude, or `python3 <path-to-ballet>/scripts/reset_plugin.py`, to refresh the plugin copy. Claude works on a copy that it does not refresh while the version is unchanged: the script reinstalls it and checks that it has every file of the clone.

Then restart open sessions.

## Uninstall

```sh
claude plugin uninstall ballet@ballet-local
rm -r ~/.claude/skills/reset-ballet
grok plugin uninstall ballet
rm ~/.vibe/plugins/ballet
```

## Developing Ballet

```sh
python3 -m unittest discover -s tests
```

Repo rules: [`AGENTS.md`](AGENTS.md).
