---
name: workshop
description: Workshop loop. By default assisted: a live session with the Dramaturg, which frames a need, a bug, feedback or an idea into ready features with the Director, and consults the Choreographer for every feature (always: S or M?, and the technical points when it touches a technical choice). With `--autopilot [<item>]`: autonomous, a Conductor session plays one line of the backlog (the first of *Next up* when none is named) with the Dramaturg, which asks the Choreographer's advice when needed (rounds bounded by `max_exchange_rounds`); its specs reach `main` by a pull request, and its issue is published `proposed` (the Director accepts it before it enters the queue) or `ready` for the work types the project skips, marked `ballet:decided-alone` when the Dramaturg decided something alone. Use as `/ballet:workshop [what to frame]` or `/ballet:workshop --autopilot [<BUG-004> | <a request>]`, from the project's home folder.
---

# Workshop

The Workshop frames a need into a feature that is ready to be played. Two modes, read from the arguments: **assisted** (the default) and **`--autopilot`**.

## Assisted (no flag)

You are the session: the Director talks to the Dramaturg, live, and nothing else starts. No Conductor, no worker, no state to keep, no message to carry.

1. Load the skill `/ballet:dramaturg` and follow it with the Director. Whatever follows the command (a need, a bug, feedback, an idea, a backlog line, "what's next?") is what they want to work on; with nothing, the Dramaturg asks.
2. The Dramaturg consults the Choreographer once for every feature, as a sub-agent of this same session (its section *Consult the Choreographer*): always the size of the ticket, S or M, with its estimate, and the technical points when the feature touches a technical choice. The size is written on the issue (`--size`), with the analogue (`Analogue: FEAT-NNN`) for an `S`, which has no plan.
3. When a feature is ready, the Dramaturg publishes its issue `ready`, after the Director's yes; if the feature depends on others (its `Depends on:` line), the script links the issue "Blocked by" them on GitHub, and Maestro will not start it before they are closed. The Workshop is over: they launch what comes next (`/ballet:rehearsal #<n>`).

## `--autopilot <item>`

Nobody is there to drive the Dramaturg: a Conductor session does.

1. Take **one** item: a line of the project's backlog (`OPP-12`, `FEAT-007`, `BUG-004`, `TASK-009`), or none: the Workshop then picks alone the first line of *Next up* that has no Workshop yet. A request that is not in the backlog yet (free text, not an ID): the Dramaturg captures it first, then frames the line it lands on; the session is named by the request's slug. More than one item: ask the Director which one to frame, and stop.
2. Load the skill `/ballet:conductor`, its section *A Workshop session (autopilot)*, and follow it, beginning with `ballet_workshop.py begin [<item>]`, or `begin --request "<the request, as the Director said it>"`.

The Dramaturg decides alone, within its perimeter, and writes down what it decided (in the issue, which then carries the label `ballet:decided-alone`), the size included (`## Decided alone`: the Director sets the field with `ballet_github.py size <issue> S|M` when they accept the proposal); it consults the Choreographer for every feature (size S or M, and the technical points), through the Conductor, as many rounds as `[escalation] max_exchange_rounds` allows; the exchange is published on the issue. Its `Depends on:` line becomes GitHub's native "Blocked by" links when the issue is published (the script says which links it made, and a dependency that no issue and no spec knows stops the Workshop before anything is created). The issue it publishes is `proposed` unless the project's `[workshop] queue_approval_skipped` lists its type (`Feature`, `Bug` or `Task`), and always `proposed` for an item the Workshop picked itself. Accepting a proposal is the Director's: they set the issue's `Ballet status` to `ready`, and the next `/ballet:rehearsal #<n>` (or the observer, later) plays it. One session per item; two items get two Conductors side by side.
