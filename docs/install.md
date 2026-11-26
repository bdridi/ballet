# Install, update, uninstall

The short version is in the [README](../README.md#get-started).

## Requirements

- macOS with Orca installed and running.
- At least one authenticated CLI: Claude Code (`claude`), Grok (`grok`) or Mistral Vibe (`vibe`).
- The GitHub CLI (`gh`), authenticated, and a GitHub remote for each project.
  - Personal repo: `gh` needs the `user` scope (`gh auth refresh -h github.com -s user`), so Ballet can create its issue types and fields.
  - Organization repo: you must be one of its owners.
- A CI on the project's pull requests that runs its proof command. Ballet never merges without a green CI (no CI counts as not green).
- Python 3.11 or later (standard library only).
- A clone of this repo, e.g. `~/Workspace/ballet`. Below, `<path-to-ballet>` is that path.

## Install the plugin

```sh
python3 <path-to-ballet>/scripts/reset_plugin.py
```

It installs Ballet for every CLI found on the machine:

- **Claude Code**: adds the local marketplace `ballet-local`, installs `ballet@ballet-local` (user scope), checks the installed copy, and writes the user skill `reset-ballet` in `~/.claude/skills/`.
- **Mistral Vibe**: links `~/.vibe/plugins/ballet` to the clone. Vibe reads it directly, so there is nothing to refresh. The first time Vibe runs in a project, accept "Trust this folder?", otherwise it loads neither `AGENTS.md` nor the project's skills.
- **Grok**: updates the plugin, or installs it from the clone (`--trust`: Grok requires explicit consent; Ballet contains no hook and no MCP server).

To try Claude without installing: `claude --plugin-dir <path-to-ballet>`.

Check: run `/ballet:dramaturg` in one of the CLIs. The Dramaturg should introduce itself. `/dramaturg` without the prefix also works in Claude and Vibe, as long as no other skill has that name.

## Set up the machine

`/ballet:setup`, once, with the Orca app open. See [Maestro, the Monitor and the machine](maestro.md#set-up-the-machine-balletsetup).

## Bootstrap a project

`/ballet:init-project`, once, in the project's home folder (its repo). It asks for the specs space, the proof command (the one that says "it's green") and, if it is not English, the specs language. It creates:

- `.ballet/config.toml`: the project profile (see [Configuration](configuration.md));
- `AGENTS.md` and `CLAUDE.md` (which imports `AGENTS.md`), without overwriting existing files;
- `.claude/skills/`, and the `.agents/skills` link to it, so that Vibe sees the project's skills;
- on GitHub, the issue types and fields Ballet's queue reads (see [Configuration](configuration.md#github-issue-types-and-fields)); `--no-github` skips this step.

## Update

After a `git pull` (or a change) in the clone:

1. `/reset-ballet` in Claude, or `python3 <path-to-ballet>/scripts/reset_plugin.py`. Claude works on a copy of the plugin, which it does not refresh while the version is unchanged: the script uninstalls it, reinstalls it and checks that the copy has every file of the clone. For Vibe, it relinks if needed; for Grok, it runs `grok plugin update`. It also rewrites the `reset-ballet` skill.
2. `/ballet:setup upgrade`, to restart Maestro and the Monitor on the new version (see [Maestro](maestro.md#upgrade-balletsetup-upgrade)).
3. Restart open sessions.

## Uninstall

```sh
claude plugin uninstall ballet@ballet-local
rm -r ~/.claude/skills/reset-ballet
grok plugin uninstall ballet
rm ~/.vibe/plugins/ballet
```
