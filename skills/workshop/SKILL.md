---
name: workshop
description: Workshop loop. By default assisted: a live session with the Dramaturg, which frames a need, a bug, feedback or an idea into ready features with the Director, and asks the Choreographer's advice when a feature touches a technical choice. With `--autopilot <item>`: autonomous, a Conductor session plays one line of the backlog with the Dramaturg alone, its specs reach `main` by a pull request, and its issue is published `proposed` (the Director accepts it before it enters the queue) or `ready` for the work types the project skips. Use as `/ballet:workshop [what to frame]` or `/ballet:workshop --autopilot <BUG-004>`, from the project's home folder.
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

1. Take **one** item: a line of the project's backlog (`OPP-12`, `FEAT-007`, `BUG-004`, `TASK-009`). No item, or more than one: ask the Director which one to frame, and stop (a Workshop that picks alone in the backlog does not exist yet). A request that is not in the backlog yet is captured first, in an assisted Workshop, which gives it its number.
2. Load the skill `/ballet:conductor`, its section *A Workshop session (autopilot)*, and follow it, beginning with `ballet_workshop.py begin <item>`.

The Dramaturg decides alone, within its perimeter, and writes down what it decided; the issue it publishes is `proposed` unless the project's `[workshop] queue_approval_skipped` lists its type. Accepting a proposal is the Director's: they set the issue's `Ballet status` to `ready`, and the next `/ballet:rehearsal #<n>` (or the observer, later) plays it. One session per item; two items get two Conductors side by side.
