---
name: workshop
description: Workshop loop. By default assisted: a live session with the Dramaturg, which frames a need, a bug, feedback or an idea into ready features with the Director, and asks the Choreographer's advice when a feature touches a technical choice. With `--autopilot [<item>]`: autonomous, a Conductor session plays one line of the backlog (the first of *Next up* when none is named) with the Dramaturg, which asks the Choreographer's advice when needed (rounds bounded by `max_exchange_rounds`); its specs reach `main` by a pull request, and its issue is published `proposed` (the Director accepts it before it enters the queue) or `ready` for the work types the project skips, marked `ballet:decided-alone` when the Dramaturg decided something alone. Use as `/ballet:workshop [what to frame]` or `/ballet:workshop --autopilot [<BUG-004> | <a request>]`, from the project's home folder.
---

# Workshop

The Workshop frames a need into a feature that is ready to be played. Two modes, read from the arguments: **assisted** (the default) and **`--autopilot`**.

## Assisted (no flag)

You are the session: the Director talks to the Dramaturg, live, and nothing else starts. No Conductor, no worker, no state to keep, no message to carry.

1. Load the skill `/ballet:dramaturg` and follow it with the Director. Whatever follows the command (a need, a bug, feedback, an idea, a backlog line, "what's next?") is what they want to work on; with nothing, the Dramaturg asks.
2. The Dramaturg consults the Choreographer once, as a sub-agent of this same session, when a feature touches a technical choice (its section *Consult the Choreographer*). Never otherwise.
3. When a feature is ready, the Dramaturg publishes its issue `ready`, after the Director's yes. The Workshop is over: they launch what comes next (`/ballet:rehearsal #<n>`).

## `--autopilot <item>`

Nobody is there to drive the Dramaturg: a Conductor session does.

1. Take **one** item: a line of the project's backlog (`OPP-12`, `FEAT-007`, `BUG-004`, `TASK-009`), or none: the Workshop then picks alone the first line of *Next up* that has no Workshop yet. A request that is not in the backlog yet (free text, not an ID): the Dramaturg captures it first, then frames the line it lands on; the session is named by the request's slug. More than one item: ask the Director which one to frame, and stop.
2. Load the skill `/ballet:conductor`, its section *A Workshop session (autopilot)*, and follow it, beginning with `ballet_workshop.py begin [<item>]`, or `begin --request "<the request, as the Director said it>"`.

The Dramaturg decides alone, within its perimeter, and writes down what it decided (in the issue, which then carries the label `ballet:decided-alone`); it asks the Choreographer's advice when the feature touches a technical choice, through the Conductor, as many rounds as `[escalation] max_exchange_rounds` allows; the exchange is published on the issue. The issue it publishes is `proposed` unless the project's `[workshop] queue_approval_skipped` lists its type (`Feature`, `Bug` or `Task`), and always `proposed` for an item the Workshop picked itself. Accepting a proposal is the Director's: they set the issue's `Ballet status` to `ready`, and the next `/ballet:rehearsal #<n>` (or the observer, later) plays it. One session per item; two items get two Conductors side by side.
