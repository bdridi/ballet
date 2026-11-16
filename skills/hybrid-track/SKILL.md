---
name: hybrid-track
description: Piece v0. The Director has framed the work with the Dramaturg (interactive Workshop); this launches, in auto with the Conductor, one issue, a queue of issues, or ready features (the Choreographer plans them and creates their issues and slices), one Rehearsal at a time up to each Premiere, unless it escalates. Use as `/ballet:hybrid-track #<issue>… | FEAT-NNN… [--plan review|auto]`, from the project's home folder.
---

# hybrid-track

The Director's call to this Piece is their Workshop stamp: from here, the Rehearsals run in auto, one at a time, in the order given.

1. Take the items from the arguments, in their order, and the plan mode if given:
   - `#12` or `12`: an existing issue;
   - `FEAT-002` (or `BUG-NNN`, `TASK-NNN`): a ready feature; the Choreographer plans it and creates its issue and slices;
   - `--plan review` (the default, `[escalation] plan_approval = true`): once the Choreographer has published a plan, the queue stops until the Director labels the planned issue `ballet:plan-approved`; `--plan auto`: no stop.

   Examples: `#12` · `#12 #13 #14` · `FEAT-002 FEAT-003` · `FEAT-002 --plan auto`. No item: ask the Director what to play, and stop.
2. Load the skill `/ballet:conductor` and follow it, beginning with `run <items…> [--plan review|auto]`, items and flag passed as given.

Everything is sequential: one Rehearsal open at a time; each one starts from `main` after the previous Premiere, so a feature is planned on the code its predecessors left. The slices of a feature play before the next item. An escalation pauses the queue; `resume` picks it up.

Validation is **auto**: the Critic stamps. The Conductor merges as soon as the verdict is `APPROVED` and the CI is green, and escalates otherwise.
