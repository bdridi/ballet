# Ballet

A common method to make coding agents (Claude, Grok, Mistral Vibe…) work as a chain, on Orca.
Ballet is a plugin: install it once, and all your projects benefit.

You frame the work with an agent; then Ballet plans it, codes it, reviews it and merges it, one pull request at a time, and stops to ask you whenever something needs your decision.

> Status: under construction (v0.31.0), used on real projects in sequential mode, with a single repo per project. The full method is described in [`PRD.md`](PRD.md), what is shipped in [`release.md`](release.md), what comes next in [`opportunities.md`](opportunities.md) (all in French for now).

## How it works

You are the **Director**. Four roles do the work, each one an agent in its own session:

| Role | Does | Touches |
|---|---|---|
| **Dramaturg** | frames a need with you into ready features (what and why), then publishes each one's issue, typed and `ready`, with no plan | the specs space; GitHub only to publish that issue |
| **Choreographer** | writes the technical plan on the feature's issue, cut into slices when it is big; writes the ADRs | ADRs and `AGENTS.md` only |
| **Dancer** | codes the plan, test first, one commit per task | the code |
| **Critic** | reviews the pull request and returns a verdict | nothing (read-only) |

The **Conductor** runs them on Orca for you: it starts each role, carries their questions and answers, publishes everything on GitHub (issue comments, pull request, review) and merges once the Critic approves and the CI is green. A deterministic script checks after each role that it stayed within its perimeter; a role that oversteps is sent back once, then you decide.

One issue played this way is a **Rehearsal**; its merge is the **Premiere**. You hand one item to a Conductor with `/ballet:rehearsal`: it plays it, Rehearsal after Rehearsal, up to its last Premiere.

## Requirements

- macOS with Orca installed and running.
- At least one of these CLIs, authenticated: Claude Code (`claude`), Grok (`grok`), Mistral Vibe (`vibe`).
- The GitHub CLI (`gh`), authenticated, and a GitHub remote for each project. For a repo owned by your personal account, `gh` needs the `user` scope, so that Ballet can create its issue types and fields: `gh auth refresh -h github.com -s user`. For a repo owned by an organization, you need to be one of its owners.
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

### Set up the machine (`/ballet:setup`)

Once the plugin is installed, `/ballet:setup` prepares the machine in one go, on your own machine with the Orca app open: it checks the tools, reinstalls the plugin, registers your projects (an alias and a path each, in `~/.ballet/maestro.toml`, and in Orca), offers `/ballet:init-project` to those without a profile, and creates **Maestro's mailbox** (`ballet_maestro.py mailbox`): an empty Orca terminal and its Run, created once. From then on, every Conductor posts a `status` message there when it escalates or finishes (`antimurphy#12 · escalate`). Then open **`/ballet:maestro`**: the session you talk to. It takes the lease on the mailbox (`ballet_maestro.py claim`: only one session reads it, since reading consumes the messages; `--take-over` replaces a dead or cleared one), tells you *While you were away: …*, then sleeps on the mailbox (`wait`, in the background) and wakes at each escalation to tell you why, with the links and what to decide. `status` lists each project's open sessions and the Conductors Maestro launched, with the state of their terminals; `tell <project>#<item> <answer>` carries your answer to that Conductor's terminal; `launch <project> <item>` (or `launch <project> --workshop [<item>]`) starts a Conductor on your word: `ballet_launch.py` opens an Orca terminal in the project and runs `claude --remote-control '<project>#<item>' '/ballet:rehearsal #<n>'` there, so you can also open that session from your phone (Maestro gives you its Remote Control URL when it is found). Four guards come first: a known project, no Conductor already alive on the item, at most `max_running` Conductors alive (3) and `max_per_day` launches a day (10), both set in the `[limits]` table of `~/.ballet/maestro.toml`. Each Conductor is a line of `~/.ballet/conductors.json` (project, item, kind, terminal, URL, start, last event, `running` or `finished`). `BALLET_CONDUCTOR_COMMAND` replaces `claude` to try a launch without tokens. The **Monitor** (`ballet_monitor.py`, a script with no LLM, started by `/ballet:setup` in its own Orca terminal `ballet-monitor` through `ballet_maestro.py monitor`) is Maestro's eyes: every 3 minutes it reads each project's GitHub queue and the Conductors' terminals, and writes into the mailbox an item that turned `ready` (`antimurphy#12 · ready`, with its type, title, priority and link; the items already ready when it first looks at a project come in one message) or a Conductor whose terminal vanished (`antimurphy#12 · gone`, high priority; its registry line becomes `gone`), or a Conductor Maestro launched that finished but is still open after `close_finished_after_minutes` (`[conductors]` in `~/.ballet/maestro.toml`, 10 by default, 0 never: `antimurphy#12 · finished`); Maestro then closes it with `ballet_launch.py close antimurphy#12` (`DECISION: close`), which closes its terminal and marks its line `closed`. It launches nothing and never talks to you. Maestro decides what to do with a `ready` item by a rule a script computes: `auto_launch = ["Task", "Bug"]` under `[projects.<alias>]` in `~/.ballet/maestro.toml` lists the types launched on their own (empty by default: Maestro always asks you), and `pause` / `resume` set or lift the flag `~/.ballet/auto_launch_paused`, during which nothing leaves on its own. Dependencies between items are GitHub's native "Blocked by" links, which the Dramaturg sets when it publishes an issue (a `Depends on: FEAT-002` line in the specs): an item starts only when all its blockers are closed, the Monitor wakes Maestro only when an item becomes launchable (`ready` with no open blocker), and `ballet_launch.py` refuses a blocked item (`--ignore-blockers`, on the Director's explicit word only). `wait` and `recap` write `DECISION: launch`, `DECISION: wait (blocked by #M, open)` or `DECISION: ask the Director (<reason>)` under each ready item; `ready` lists the ready items no Conductor plays yet, in queue order (a launch refused by a limit stays there until a `done` or a `gone` frees a slot). `/ballet:setup` also starts Maestro itself (`ballet_maestro.py maestro`, idempotent): an Orca terminal titled `maestro` runs `claude --remote-control 'ballet maestro' '/ballet:maestro'`, so Maestro is reachable from the Claude app (Mac or phone) as « ballet maestro »; it creates nothing when that terminal is alive or when another Maestro session holds a live lease, and its tab must stay open (`--take-over` only on the Director's yes). On your word, `stop <project>#<item>` stops a Conductor that is still working and keeps its work (`ballet_launch.py stop`): its terminal is closed, its Orca workers are stopped, its Rehearsal (or Workshop) and the issue's Ballet status become `escalated`, and the state, branch, worktree and pull request stay; it frees a slot (`stopped` in the registry) and is never relaunched on its own; resuming it mid-flight is still to come (OPP-80). `restart` (`ballet_restart.py when-idle`) clears Maestro's own context: it pauses auto launch, waits until no Conductor is working (one paused on an escalation does not count) and Maestro sleeps on its mailbox, then replaces the session in its Orca tab with a fresh one that takes the lease and opens with *While you were away*, and lifts the pause; it gives up after four hours (`maestro · restart abandoned` in the mailbox). The headless mode is still to come (OPP-74). Every step can be rerun.

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
- `.ballet/run/` in the `.gitignore`: Ballet keeps its state and journal there;
- on GitHub, for the repo's owner (your account or your organization, shared by all its repos): the issue type `Slice` next to `Task`, `Bug` and `Feature`, and four issue fields, `Ballet status` (`proposed`, `ready`, `in-rehearsal`, `plan-review`, `escalated`, `done`), `Rehearsal mode` (`assisted`, `autopilot`), `Plan approval` (`required`, `skipped`) and `Priority`. Only what is missing is created, nothing is changed; a field that exists without all its options is reported, to complete in Settings → Planning. Ballet's queue reads them: the Conductor reads `Rehearsal mode` and `Plan approval` and keeps `Ballet status` up to date; `--no-github` skips this step.

To prepare the GitHub issue types and fields again, e.g. for a project whose remote did not exist yet:

```sh
python3 <path-to-ballet>/scripts/ballet_planning.py <project-folder>
```

To check the configuration by hand:

```sh
python3 <path-to-ballet>/scripts/ballet_config.py check <project-folder>
```

## 2. Frame the work

```
/ballet:dramaturg
```

Talk it through with the Dramaturg: a need, a bug, feedback, or "what's next?". It keeps the backlog and writes each feature in the specs space until it is **ready** (`features/FEAT-NNN-*.md`). Nothing starts on its own at the end: launching the Rehearsal is your go.

### Frame it without you: the autopilot Workshop

A line of your backlog (`BUG-004`, `FEAT-007`, `OPP-12`, `TASK-009`) can also be framed with nobody in the loop: from the project's home folder, in Orca,

```
/ballet:workshop --autopilot BUG-004
```

A Conductor session (`.ballet/run/workshop-BUG-004.json`) starts the Dramaturg in its own worktree, on the branch `workshop/BUG-004`. The Dramaturg decides within its perimeter and writes down what it decided. When it reports, Ballet's policy checks that only the specs space changed, its specs reach `main` by a pull request merged straight away (no Critic and no CI: specs are not code), and its issue is published:

- **`proposed`** (the default): the issue waits for you. Read it and its *Decided alone* section (the Dramaturg's business decisions, with its reasons; the issue then carries the label `ballet:decided-alone`), then set its `Ballet status` to `ready` on GitHub: it enters the queue.
- **`ready`** straight away, for the work types your profile skips: `[workshop] queue_approval_skipped = ["Bug"]` (`Feature`, `Bug` or `Task`; empty by default). Start with `Bug` or `Task`: a bug has the spec for referee, while a feature makes the Dramaturg guess some business, which then reaches the Rehearsal without your review. `Feature` is allowed once you accept that; the label still tells you what was decided alone.

When a feature touches a technical choice (a dependency, a data model, a contract, several repos, its size), the Dramaturg asks the Choreographer's advice before writing, through the Conductor: the Choreographer reads, answers, and writes nothing. The rounds are bounded only by `[escalation] max_exchange_rounds` (3 by default, your profile overrides it); each question and answer is in the journal and is published as a comment on the issue.

With no item, `/ballet:workshop --autopilot` picks the first line of the backlog's *Next up* that has no Workshop yet. What it picks alone is always `proposed`, whatever your profile skips.

A request that is not in your backlog yet works too: `/ballet:workshop --autopilot "stock goes negative after a double cancel"`. The session is named by its slug (`workshop/stock-goes-negative-after-a-double`); the Dramaturg captures the request in the backlog first, then frames that line. The journal keeps one key per session, never renamed: its `published` event links the slug to the backlog line and to the issue.

If the Dramaturg cannot frame the item (a missing backlog line, a word whose UI wording only you can name), or the merge or the publication fails, the Conductor stops and tells you why; once fixed, tell it to resume. Without `--autopilot`, `/ballet:workshop` is the assisted Workshop, which needs no session: a live conversation between you and the Dramaturg (the same as `/ballet:dramaturg`), which asks the Choreographer's advice when a feature touches a technical choice.

## 3. Run a Rehearsal

From the project's home folder, in Orca, hand one item to a Conductor:

```
/ballet:rehearsal #12          # a Feature, a Bug or a Task issue
/ballet:rehearsal FEAT-002     # a ready feature that has no issue yet: planned, then coded, reviewed and merged
```

What happens:

- **One item per Conductor session.** The session (`.ballet/run/session-12.json`) plays the item, then its slices, one Rehearsal at a time, and ends at its last Premiere. Each Rehearsal starts from `main` after the previous merge. Another item gets its own Conductor; an item already in a session is refused.
- **The mode is on the issue**: its `Rehearsal mode` field (empty: `assisted`). In `assisted`, whether the plan waits for you is its `Plan approval` field (`required` or `skipped`), or else your project's profile (`[rehearsal] plan_approval`, `true` by default); a feature with no issue follows the profile, and `autopilot` never waits. The Conductor keeps its `Ballet status` up to date: `in-rehearsal`, `plan-review`, `escalated`, `done`.
- **A feature is planned first.** The Choreographer reads its issue (published by the Dramaturg) with the code, settles the technical choices, and writes the plan on it, cut into slices when one pull request would be too big. It asks the Dramaturg when the feature has gaps, and you when neither of them can settle something. The slices then play one after the other. Its ADRs ship with the first slice.
- **An issue that already has its plan** goes straight to the Dancer; one without a plan is planned first, like a feature.
- **You review the plan** when it waits for you: once the Choreographer has published it, the session stops, and you discuss it with the Choreographer through the Conductor until you approve it (see below). Otherwise it goes on.
- **Then, for each issue**: the Dancer codes, the script runs the proof (and the mutation test, if your project declares one), the Critic reviews (up to 2 round trips), and the pull request is merged when the Critic approves and the CI is green. The issue is closed, and its parent after its last slice.

The Conductor tells you what it does as it goes, and stops when the item's last slice is merged or when it needs you.

## 4. When the Conductor needs you

Any stop pauses the session; the Conductor tells you why and what to decide. A plan review is a conversation with the Conductor; your other decisions go through GitHub labels, then you tell the Conductor to resume ("go on", "resume"):

| The Conductor says | You |
|---|---|
| a plan to review | read the issue and its slices, then tell the Conductor: a question for the Choreographer (it answers, the plan stays as is), changes to make (it amends the plan and its slices, and you review again), or that you approve it (the Dancer starts). Every exchange is published on the issue |
| a role asks you a question | answer it in the conversation: the Conductor carries your answer back |
| the Critic escalates, too many round trips, a policy violation… | on the pull request: `ballet:approved` to merge it, or `ballet:rejected` with a comment saying what to fix (sent to the Dancer), then resume |
| the diff is over the limit (strict mode) | `ballet:size-accepted` to send it to the Critic anyway, or `ballet:rejected` with a comment, then resume |
| the mutation test stayed red, ran over an hour, or failed | look at its log (`.ballet/run/<ID>/mutation-*.log`); fix the tool or its config, or decide on the pull request as above |
| the CI failed, or ran too long | fix or rerun it; once green, ask the Conductor to retry the merge |
| the session stopped before an item (e.g. an issue title without its `FEAT-NNN` prefix) | fix the cause, then resume |

To change a plan before approving it, edit the issue yourself. To drop a session, delete its `.ballet/run/session-<item>.json`.

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

Then open http://127.0.0.1:7700 (`--port` to change it). For each project: its Conductor sessions (the item it was given and its remaining slices), then the program (what waits on GitHub: `Feature`, `Bug` and `Task` issues whose Ballet status is `ready`, by priority then age), what was played, and its Rehearsals. If GitHub does not answer, the page says so. For each Rehearsal: what you have to do when it waits for you, the phase it has reached (plan, code, review, Premiere), the round trips and the diff size against their limits, who plays which role, and the whole thread: every message between the roles in full, what the Conductor handed to each one, the policy checks and every step of the script. Once a Rehearsal is over, its **frictions** (escalations, Critic rejections, red proofs or mutations, refused reports, workers reminded, policy refusals, a diff over the limit, and its duration) are kept in its state and in the journal: the Stage shows them on the Rehearsal and on its session, finished sessions included, and the session's `done` gives them to Maestro. It listens on 127.0.0.1 only and changes nothing.

## Settings you may tune

In the project's `.ballet/config.toml` (every key is optional; the defaults are in the plugin's [`config.toml`](config.toml)):

```toml
[roles.dancer]                  # which CLI and model plays each role
cli = "claude"
model = "sonnet"                # the Critic must differ from the Dancer: another CLI, or another model

[escalation]
max_round_trips = 2             # Dancer ↔ Critic round trips before it comes to you
max_diff_lines = 1500           # lines changed by a pull request; over it, the pull request is marked oversized
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
