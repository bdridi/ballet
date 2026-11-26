# Rehearsals and Workshops

Reference for playing an item. The short version is in the [README](../README.md).

## Run a Rehearsal

From the project's home folder, in Orca, hand one item to a Conductor:

```
/ballet:rehearsal #12          # a Feature, a Bug or a Task issue
/ballet:rehearsal FEAT-002     # a ready feature that has no issue yet: planned, then coded, reviewed and merged
```

- **One item per Conductor session.** The session (kept in Ballet's base, under `#12`) plays the item, then its slices, one Rehearsal at a time, and ends at its last Premiere. Each Rehearsal starts from `main` after the previous merge. Another item gets its own Conductor; an item already in a session is refused.
- **For each issue**: the Dancer codes, the script runs the proof (and the mutation test, if your project declares one), the Critic reviews (up to 2 round trips), and the pull request is merged when the Critic approves and the CI is green. The issue is closed, and its parent after its last slice.
- The Conductor tells you what it does as it goes, and stops when the item's last slice is merged or when it needs you.

Maestro can launch Conductors for you: see [Maestro](maestro.md).

## The mode and the plan

The mode is on the issue, in its `Rehearsal mode` field (empty: `assisted`). The Dramaturg sets it when you ask (`ballet_github.py publish … --mode autopilot`, or `mode <issue> autopilot` on an issue already published); you can also set it by hand on GitHub.

- `autopilot`: the plan never waits for you.
- `assisted`: whether the plan waits for you is the issue's `Plan approval` field (`required` or `skipped`), else your profile (`[rehearsal] plan_approval`, `true` by default). A feature with no issue follows the profile.

The Conductor keeps the issue's `Ballet status` up to date: `in-rehearsal`, `plan-review`, `escalated`, `done`.

| The issue is | What happens |
|---|---|
| a feature | The Choreographer reads its issue (published by the Dramaturg) with the code, settles the technical choices, and writes the plan on it, cut into **two or three slices** when one pull request would be too big (never a single slice: otherwise the plan is written on the feature's issue). It asks the Dramaturg when the feature has gaps, and you when neither can settle something. The slices then play one after the other. Its ADRs ship with the first slice. |
| an issue that already has its plan | straight to the Dancer |
| an issue without a plan | planned first, like a feature |
| a small ticket (Size `S`) | no plan, see below |

### Plan review

When the plan waits for you, the session stops once the Choreographer has published it. You discuss it with the Choreographer through the Conductor until you approve it: a question (it answers, the plan stays as is), changes to make (it amends the plan and its slices, and you review again), or your approval (the Dancer starts). Every exchange is published on the issue. To change a plan before approving it, you can also edit the issue yourself.

### Size: a small ticket has no plan

The `Size` field is `S` or `M`. Empty, a bug or a task plays `S` and a feature plays `M`. There is no `L`: a big ticket is an `M`, cut into slices.

A ticket is `S` only when all of this is true (at the slightest doubt it is `M`):

- a shipped feature is its analogue (`Analogue: FEAT-NNN` on the issue);
- its decisions are written (ADR, rule in `AGENTS.md`) and nothing else is left to decide;
- no new aggregate, entity, port, table, migration or glossary term;
- under about 1,200 lines, tests included.

An `S` Rehearsal starts with the Dancer, from the issue and its analogue; it writes its own tasks. No plan is written or reviewed, even in `assisted`. Its questions still go to the Choreographer, who answers from the issue and the analogue. The Critic judges the diff against the criteria, the analogue, the rules and the ADRs. Proof, mutation, diff size, Critic and Premiere do not change.

The Dramaturg consults the Choreographer on every feature and always asks "S or M?"; you decide. Set the size on publication (`ballet_github.py publish … --size S`) or on an issue already published (`size <issue> S|M`).

## When the Conductor needs you

Any stop pauses the session; the Conductor tells you why and what to decide. Most answers go through Maestro (`tell`), the others through GitHub labels. Then tell the Conductor to resume ("go on", "resume").

| The Conductor says | You |
|---|---|
| a plan to review | see *Plan review* above |
| `question: …` (a role asks you) | answer in the conversation: the Conductor carries your answer back. Without a question waiting, an answer is refused, and the refusal tells you to use `override` |
| `failure: …` (a worker stopped on an error, such as Orca's 5-hour limit, or escalates) | `tell --override <project>#<item> <your reason>`: the worker restarts in its own session, with its context and your words |
| `policy: …` (a role broke the rules twice) | `override` with your reason: the branch is received as it is, once. Or `ballet:rejected` with a comment on the pull request, then resume |
| `size: …` (the diff is over the limit, strict mode) | `override` (the pull request goes to the Critic), or `ballet:size-accepted`, or `ballet:rejected` with a comment, then resume |
| `turns: …` (too many round trips, a red proof or mutation too many times, too many rounds on a subject) | `override`: one more turn for the Dancer, who takes your words first; if it fails again, you hear of it again |
| the Critic escalates, or a policy violation you want sent back | on the pull request: `ballet:approved` to merge it, or `ballet:rejected` with a comment saying what to fix (sent to the Dancer), then resume |
| the mutation test stayed red, ran over an hour, or failed | read its log (`~/.ballet/projects/<alias>/<ID>/mutation-*.log`); fix the tool or its config, or decide on the pull request as above |
| the CI failed, or ran too long | fix or rerun it; once green, ask the Conductor to retry the merge |
| the session stopped before an item (e.g. an issue title without its `FEAT-NNN` prefix) | fix the cause, then resume |

To check the state at any time, ask the Conductor, or run `python3 <path-to-ballet>/scripts/ballet_rehearsal.py status`.

To drop a session: `python3 <path-to-ballet>/scripts/ballet_store.py drop session '#12'` from the project's home (its journal stays).

To run the mutation test by hand, as a Rehearsal would on your branch: `python3 <path-to-ballet>/scripts/ballet_mutation.py run` from the project's home (`--force` when `[mutation] enabled = false`).

## Workshops

A Workshop turns a need into a ready feature, with the Dramaturg.

### Assisted (the default)

`/ballet:workshop`, or `/ballet:dramaturg`: a live conversation between you and the Dramaturg. It needs no session and no Conductor. When a feature touches a technical choice, the Dramaturg asks the Choreographer's advice. Its cost is posted as a comment on the issue it publishes.

### Autopilot: framed without you

A line of your backlog (`BUG-004`, `FEAT-007`, `OPP-12`, `TASK-009`) can be framed with nobody in the loop:

```
/ballet:workshop --autopilot BUG-004
```

A Conductor session starts the Dramaturg in its own worktree, on the branch `workshop/BUG-004`. The Dramaturg decides within its perimeter and writes down what it decided. When it reports, Ballet's policy checks that only the specs space changed, its specs reach `main` by a pull request merged straight away (no Critic and no CI: specs are not code), and its issue is published:

- **`proposed`** (the default): the issue waits for you. Read it and its *Decided alone* section (the Dramaturg's business decisions, with its reasons; the issue carries the label `ballet:decided-alone`), then accept it: the Dramaturg does it for you (`ballet_github.py accept <issue>`, `proposed` to `ready`), or set its `Ballet status` to `ready` on GitHub. It enters the queue.
- **`ready`** straight away, for the work types your profile skips: `[workshop] queue_approval_skipped = ["Bug"]` (`Feature`, `Bug` or `Task`; empty by default). Start with `Bug` or `Task`: a bug has the spec for referee, while a feature makes the Dramaturg guess some business, which then reaches the Rehearsal without your review. The label still tells you what was decided alone.

With no item, `/ballet:workshop --autopilot` picks the first line of the backlog's *Next up* that has no Workshop yet. What it picks alone is always `proposed`, whatever your profile skips.

A request that is not in your backlog yet works too: `/ballet:workshop --autopilot "stock goes negative after a double cancel"`. The Dramaturg captures the request in the backlog first, then frames that line. The session is named by its slug (`workshop/stock-goes-negative-after-a-double`).

When a feature touches a technical choice (a dependency, a data model, a contract, several repos, its size), the Dramaturg asks the Choreographer's advice before writing, through the Conductor. The Choreographer reads, answers, and writes nothing. The rounds are bounded by `[escalation] max_exchange_rounds` (3 by default); each question and answer is in the journal and published as a comment on the issue.

If the Dramaturg cannot frame the item (a missing backlog line, a word whose UI wording only you can name), or the merge or the publication fails, the Conductor stops and tells you why; once fixed, tell it to resume.
