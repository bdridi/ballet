# Ballet

A common method to make coding agents (Claude, Grok, Mistral Vibe) work as a chain, on Orca.
Ballet is a plugin: install it once, and all your projects benefit.

> Status: under construction (v0.8.1). Today the plugin provides the `dramaturg`, `choreographer`, `dancer` and `critic` skills, the common rules (`tdd`, `bdd`, `ddd`, `clean-code`), the specs space templates (`templates/`) and project bootstrapping (`init-project`). The full method is described in [`PRD.md`](PRD.md), the plan in [`TASKS.md`](TASKS.md) (both in French for now).

## Requirements

- macOS with Orca installed and running.
- At least one of these CLIs, authenticated: Claude Code (`claude`), Grok (`grok`), Mistral Vibe (`vibe`).
- Python 3.11 or later (standard library only).
- A clone of this repo, e.g. `~/Workspace/ballet`. In the commands below, replace `<path-to-ballet>` with that path.

## Installation

One command installs Ballet for every CLI found on the machine (Claude Code, Mistral Vibe, Grok):

```sh
python3 <path-to-ballet>/scripts/reset_plugin.py
```

What it does:

- **Claude Code**: adds the local marketplace `ballet-local`, installs `ballet@ballet-local` (user scope), checks the installed copy, and writes the user skill `reset-ballet` in `~/.claude/skills/`.
- **Mistral Vibe**: links `~/.vibe/plugins/ballet` to the clone. Vibe reads it directly, so there is nothing to refresh; the `reset-ballet` skill is Claude only (in Vibe, run the script).
- **Grok**: updates the plugin, or installs it from the clone (`--trust`: Grok requires explicit consent; Ballet contains no hook and no MCP server).

The first time Vibe runs in a project, it asks to trust the folder ("Trust this folder?"): accept, otherwise it loads neither `AGENTS.md` nor the project's skills.

To try Claude without installing: `claude --plugin-dir <path-to-ballet>`.

## Check the installation

In one of the CLIs, run:

```
/ballet:dramaturg
```

The Dramaturg should introduce itself. `/dramaturg` without the prefix also works in Claude and Vibe, as long as no other skill has that name.

## Bootstrap a project

In the project's home folder (the single repo, or the specs repo for a multi-repo project):

```
/ballet:init-project
```

The skill asks for the specs space, the proof command (the one that says "it's green") and, if it is not English, the specs language. It then creates:

- `.ballet/config.toml`: the project profile (repos, proof, rules, specs language, routing overrides);
- `AGENTS.md` and `CLAUDE.md` (which imports `AGENTS.md`), without overwriting your existing files;
- `.claude/skills/` and the `.agents/skills` link to that folder, so that Vibe sees the project's skills.

To check the configuration by hand:

```sh
python3 <path-to-ballet>/scripts/ballet_config.py check <project-folder>
```

## Watch the Rehearsals (concept)

A local, read-only page that shows what happens in a project, live and in history (stage, score of the journal, replay, season). It reads `.ballet/run/` and listens on 127.0.0.1 only.

```
python3 <path-to-ballet>/scripts/ballet_stage.py <project-folder>
python3 <path-to-ballet>/scripts/ballet_stage.py --scan <folder-of-projects>
```

Then open http://127.0.0.1:7700 (`--port` to change it). It is a first sketch: see the Stage item in `TASKS.md`.

## Languages

Code is always in English. Specs are in English by default (`[project] specs_language` to change it, e.g. for a client who reads them). Text the product displays stays in the product's language: scenarios quote it verbatim, and the glossary maps each term to its code name and its UI wording. The rule is in the `ballet:ddd` skill.

## Update

After a `git pull` (or a change) in the clone, run `/reset-ballet` in Claude, or directly:

```sh
python3 <path-to-ballet>/scripts/reset_plugin.py
```

Claude works on a copy of the plugin, which it does not refresh while the version is unchanged: the script uninstalls it, reinstalls it and checks that the copy has every file of the clone. For Vibe, it relinks if needed; for Grok, it runs `grok plugin update`. It also rewrites the `reset-ballet` skill, which therefore never drifts. Then restart open sessions.

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
