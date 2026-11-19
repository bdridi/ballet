# Ballet

A common method to make coding agents (Claude, Grok, Mistral Vibe…) work as a chain, on Orca.
Ballet is a plugin: install it once, and all your projects benefit.

You frame the work with an agent; then Ballet plans it, codes it, reviews it and merges it, one pull request at a time, and stops to ask you whenever something needs your decision.

> Status: under construction (v0.22.0), used on real projects in sequential mode, with a single repo per project. The full method is described in [`PRD.md`](PRD.md), the plan in [`TASKS.md`](TASKS.md) (both in French for now).

## How it works

You are the **Director**. Four roles do the work, each one an agent in its own session:

| Role | Does | Touches |
|---|---|---|
| **Dramaturg** | frames a need with you into ready features (what and why) | the specs space only |
| **Choreographer** | turns a feature into a GitHub issue with a technical plan, cut into slices when it is big; writes the ADRs | ADRs and `AGENTS.md` only |
| **Dancer** | codes the plan, test first, one commit per task | the code |
| **Critic** | reviews the pull request and returns a verdict | nothing (read-only) |

The **Conductor** runs them on Orca for you: it starts each role, carries their questions and answers, publishes everything on GitHub (issue comments, pull request, review) and merges once the Critic approves and the CI is green. A deterministic script checks after each role that it stayed within its perimeter; a role that oversteps is sent back once, then you decide.

One issue played this way is a **Rehearsal**; its merge is the **Premiere**. A **Piece** is how you launch them: today, `hybrid-track`.

## Requirements

- macOS with Orca installed and running.
- At least one of these CLIs, authenticated: Claude Code (`claude`), Grok (`grok`), Mistral Vibe (`vibe`).
- The GitHub CLI (`gh`), authenticated, and a GitHub remote for each project.
- A CI on the project's pull requests that runs its proof command: Ballet never merges without a green CI (no CI counts as not green).
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

## 1. Bootstrap a project (once)

In the project's home folder (its repo):

```
/ballet:init-project
```

The skill asks for the specs space, the proof command (the one that says "it's green") and, if it is not English, the specs language. It then creates:

- `.ballet/config.toml`: the project profile (repos, proof, rules, specs language, which CLI and model plays each role, thresholds);
- `AGENTS.md` and `CLAUDE.md` (which imports `AGENTS.md`), without overwriting your existing files;
- `.claude/skills/` and the `.agents/skills` link to that folder, so that Vibe sees the project's skills;
- `.ballet/run/` in the `.gitignore`: Ballet keeps its state and journal there.

To check the configuration by hand:

```sh
python3 <path-to-ballet>/scripts/ballet_config.py check <project-folder>
```

## 2. Frame the work

```
/ballet:dramaturg
```

Talk it through with the Dramaturg: a need, a bug, feedback, or "what's next?". It keeps the backlog and writes each feature in the specs space until it is **ready** (`features/FEAT-NNN-*.md`). Nothing starts on its own at the end: launching the Piece is your go.

## 3. Run a Piece

From the project's home folder, in Orca:

```
/ballet:hybrid-track FEAT-002                  # a ready feature: planned, then coded, reviewed and merged
/ballet:hybrid-track FEAT-002 FEAT-003         # several features, in this order
/ballet:hybrid-track #12                       # an existing issue
/ballet:hybrid-track #12 #13 #14               # several issues, in this order
/ballet:hybrid-track FEAT-002 --plan auto      # without stopping for you to approve the plan
```

What happens:

- **One thing at a time.** The items form a queue, played in the order you gave. Each Rehearsal starts from `main` after the previous merge, so a feature is planned on the code its predecessors left.
- **A feature is planned first.** The Choreographer reads it with the code, settles the technical choices, and publishes the issue, cut into slices when one pull request would be too big. It asks the Dramaturg when the feature has gaps, and you when neither of them can settle something. The slices then play one after the other, before the next item of the queue. Its ADRs ship with the first slice.
- **An issue that already has its plan** goes straight to the Dancer; one without a plan is planned first, like a feature.
- **You approve each plan** (`--plan review`, the default): once the Choreographer has published it, the queue stops until you do (see below). With `--plan auto`, it goes on.
- **Then, for each issue**: the Dancer codes, the script runs the proof (and the mutation test, if your project declares one), the Critic reviews (up to 2 round trips), and the pull request is merged when the Critic approves and the CI is green. The issue is closed, and its parent after its last slice.

The Conductor tells you what it does as it goes, and stops when the whole queue is merged or when it needs you.

## 4. When the Conductor needs you

Any stop pauses the whole queue; the Conductor tells you why and what to decide. Your decisions go through GitHub labels, then you tell the Conductor to resume ("go on", "resume"):

| The Conductor says | You |
|---|---|
| a plan to review | read the issue and its slices; label the issue `ballet:plan-approved`, then resume |
| a role asks you a question | answer it in the conversation: the Conductor carries your answer back |
| the Critic escalates, too many round trips, a policy violation… | on the pull request: `ballet:approved` to merge it, or `ballet:rejected` with a comment saying what to fix (sent to the Dancer), then resume |
| the diff is over the limit (strict mode) | `ballet:size-accepted` to send it to the Critic anyway, or `ballet:rejected` with a comment, then resume |
| the mutation test stayed red, ran over an hour, or failed | look at its log (`.ballet/run/<ID>/mutation-*.log`); fix the tool or its config, or decide on the pull request as above |
| the CI failed, or ran too long | fix or rerun it; once green, ask the Conductor to retry the merge |
| the queue stopped before an item (e.g. an issue title without its `FEAT-NNN` prefix) | fix the cause, then resume |

To change a plan before approving it, edit the issue yourself. To drop the rest of a queue, delete `.ballet/run/queue.json`.

At any time, ask the Conductor for the status, or run:

```sh
python3 <path-to-ballet>/scripts/ballet_rehearsal.py status
```

## 5. Watch it play: the Stage

A local, read-only page that follows your projects live:

```sh
python3 <path-to-ballet>/scripts/ballet_stage.py <project-folder>
python3 <path-to-ballet>/scripts/ballet_stage.py --scan <folder-of-projects>
```

Then open http://127.0.0.1:7700 (`--port` to change it). For each project: the queue (played, playing, next) and its Rehearsals. For each Rehearsal: what you have to do when it waits for you, the phase it has reached (plan, code, review, Premiere), the round trips and the diff size against their limits, who plays which role, and the whole thread: every message between the roles in full, what the Conductor handed to each one, the policy checks and every step of the script. It listens on 127.0.0.1 only and changes nothing.

## Settings you may tune

In the project's `.ballet/config.toml` (every key is optional; the defaults are in the plugin's [`config.toml`](config.toml)):

```toml
[roles.dancer]                  # which CLI and model plays each role
cli = "claude"
model = "sonnet"                # the Critic must differ from the Dancer: another CLI, or another model

[escalation]
plan_approval = true            # false: plans go on without your approval (like --plan auto)
max_round_trips = 2             # Dancer ↔ Critic round trips before it comes to you
max_diff_lines = 400            # lines changed by a pull request; the Choreographer keeps each slice under two thirds
max_diff_strict = false         # true: over the limit, it stops before the Critic
ci_wait_seconds = 480           # how long the merge waits for a running CI
proof_timeout_seconds = 420     # how long the proof run on each Dancer report may take
diff_exclude = ["*.lock"]       # files left out of the count

[mutation]
enabled = true                  # false: no mutation test, the tools below stay declared
timeout_seconds = 3600          # the budget of all mutation tools, run in the background

[[repos.app.mutation]]          # a mutation tool, run after the proof on the lines the branch changed
name = "cargo-mutants"
command = "mise exec -- cargo mutants --in-diff {diff}"   # {diff} a file, {files}, {ranges} (`file:start-end`)
config = ".cargo/mutants.toml"  # where equivalent mutants are excluded, each with its reason
report = { path = "mutants.out/outcomes.json", format = "cargo-mutants" }
paths = ["crates/*"]            # optional: only the diff under these paths

[policy]
sensitive_zones = ["api/contract/*"]    # paths the Dancer must not touch (API contract, security…)

[policy.roles.choreographer]
extra_writes = ["docs/*"]       # widen a role's perimeter without rewriting the method's
```

## Languages

Code is always in English. Specs are in English by default (`[project] specs_language` to change it, e.g. for a client who reads them). Text the product displays stays in the product's language: scenarios quote it verbatim, and the glossary maps each term to its code name and its UI wording. The rule is in the `ballet:ddd` skill.

## Known limits

- Sequential only: one Rehearsal at a time (parallel runs come later).
- One repo per project for the Conductor (multi-repo projects come later).
- The roles run as Orca workers with Claude Code, Codex, Grok or OpenCode; other CLIs (Mistral Vibe…) can be used by hand, not yet by the Conductor.
- Mutation reports are read for cargo-mutants only (StrykerJS and PIT come later). Another tool still works: its exit code decides, and the Dancer gets the end of its output.

To run the mutation test by hand, as a Rehearsal would on your branch: `python3 <path-to-ballet>/scripts/ballet_mutation.py run` from the project's home folder (`--force` when `[mutation] enabled = false`).

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
