---
name: init-project
description: Bootstraps a project for Ballet (profile `.ballet/config.toml`, AGENTS.md, CLAUDE.md, `.agents/skills` link, `reset-ballet` skill). Use once, in a project's home folder, before running the chain, or when the Conductor refuses to start for lack of a profile.
---

# init-project

You bootstrap the current project, which must be its home folder (single repo, or specs repo).

1. Ask the Director, unless they already gave them:
   - the **specs space** (a folder, e.g. `docs/` or `specs/`);
   - the **proof command**, the one whose success means "it's green" (e.g. `make test`);
   - the **specs language**, only if it is not English (e.g. `fr` for a client who reads the specs).
2. Run the script, found at `../../scripts/init_project.py` relative to this skill's folder:

   ```sh
   python3 <path>/scripts/init_project.py . --specs "<specs>" --proof "<proof>"
   ```

   Options: `--specs-language fr` (default: `en`), `--rules tdd,bdd` to choose the common rules (default: `tdd,bdd,ddd,clean-code`), `--repo <name>` to name the repo.
3. Report to the Director what was created (including the project skill `reset-ballet`, which reinstalls the plugin from its clone after each change: `/reset-ballet`), what already existed (never modified), and the result of the check.
4. If `AGENTS.md` already existed, offer to add the instruction to load the common rules (see the template in `scripts/init_project.py`) without overwriting it.

This skill only handles a **single repo**: for a multi-repo project, then add one `[repos.<name>]` section per repo (`path`, `proof`, `needs`) to `.ballet/config.toml` by hand, and check:

```sh
python3 <path>/scripts/ballet_config.py check .
```

You change only these files, nothing else in the project.
