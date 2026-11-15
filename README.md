# Ballet

A common method to make coding agents (Claude, Grok, Mistral Vibe) work as a chain, on Orca.
Ballet is a plugin: install it once, and all your projects benefit.

> Status: under construction (v0.3). Today the plugin provides the `dramaturg` skill, the common rules (`tdd`, `bdd`, `ddd`, `clean-code`), the specs space templates (`templates/`) and project bootstrapping (`init-project`). The full method is described in [`PRD.md`](PRD.md), the plan in [`TASKS.md`](TASKS.md) (both in French for now).

## Requirements

- macOS with Orca installed and running.
- At least one of these CLIs, authenticated: Claude Code (`claude`), Grok (`grok`), Mistral Vibe (`vibe`).
- Python 3.11 or later (standard library only).
- A clone of this repo, e.g. `~/Workspace/ballet`. In the commands below, replace `<path-to-ballet>` with that path.

## Installation

Once per CLI you use.

### Claude Code

```sh
claude plugin marketplace add <path-to-ballet>
claude plugin install ballet@ballet-local
```

To try it without installing: `claude --plugin-dir <path-to-ballet>`.

### Mistral Vibe

Vibe has no install command: link the repo into its plugins folder.

```sh
mkdir -p ~/.vibe/plugins
ln -s <path-to-ballet> ~/.vibe/plugins/ballet
```

The first time it runs in a project, Vibe asks to trust the folder ("Trust this folder?"): accept, otherwise it loads neither `AGENTS.md` nor the project's skills.

### Grok

```sh
grok plugin install <path-to-ballet> --trust
```

(`--trust`: Grok requires explicit consent to install a plugin. Ballet contains no hook and no MCP server.)

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
- `.claude/skills/` and the `.agents/skills` link to that folder, so that Vibe sees the project's skills;
- the project skill `reset-ballet`, which reinstalls the plugin from your clone (see *Update*).

To check the configuration by hand:

```sh
python3 <path-to-ballet>/scripts/ballet_config.py check <project-folder>
```

## Languages

Code is always in English. Specs are in English by default (`[project] specs_language` to change it, e.g. for a client who reads them). Text the product displays stays in the product's language: scenarios quote it verbatim, and the glossary maps each term to its code name and its UI wording. The rule is in the `ballet:ddd` skill.

## Update

After a `git pull` (or a change) in the clone, run `/reset-ballet` from a bootstrapped project, or directly:

```sh
python3 <path-to-ballet>/scripts/reset_plugin.py
```

Claude works on a copy of the plugin, which it does not refresh while the version is unchanged: the script uninstalls it, reinstalls it and checks that the copy has every file of the clone. For Vibe, it relinks if needed; for Grok, it runs `grok plugin update`. Then restart open sessions.

## Uninstall

```sh
claude plugin uninstall ballet@ballet-local
grok plugin uninstall ballet
rm ~/.vibe/plugins/ballet
```

## Developing Ballet

```sh
python3 -m unittest discover -s tests
```

Repo rules: [`AGENTS.md`](AGENTS.md).
