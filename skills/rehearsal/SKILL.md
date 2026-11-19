---
name: rehearsal
description: Rehearsal loop. The Director has framed the work with the Dramaturg (Workshop); this hands one item to a Conductor session, a Feature, a Bug or a Task issue, or a ready feature with no issue yet (the Choreographer plans it and creates its issue and slices), and plays it, one Rehearsal at a time, up to its last Premiere, unless it escalates. The mode is the issue's `Rehearsal mode` field. Use as `/ballet:rehearsal #<issue> | FEAT-NNN`, from the project's home folder.
---

# Rehearsal

The Director's call is their stamp: from here, the Conductor plays the item they hand over, alone, up to its last Premiere.

1. Take **one** item from the arguments:
   - `#12` or `12`: an issue of type `Feature`, `Bug` or `Task` (a `Slice` follows its feature: hand over the feature);
   - `FEAT-002` (or `BUG-NNN`, `TASK-NNN`): a ready feature that has no issue yet; the Choreographer plans it and creates its issue and slices.

   No item, or more than one: ask the Director which one to play, and stop. There is no flag: the mode is the issue's `Rehearsal mode` field (empty: `assisted`; a feature with no issue plays `assisted`). In `assisted`, the plan waits for the Director's review when the issue's `Plan approval` field says `required`, or, when it is empty, when the profile's `[rehearsal] plan_approval` is `true` (the default); `autopilot` never waits.
2. Load the skill `/ballet:conductor` and follow it, beginning with `begin <item>`, the item passed as given.

One session per item: its Rehearsals play one at a time, its slices in the plan's order, each one from `main` after the previous Premiere. Another item gets its own session, in another Conductor. An escalation pauses the session; `resume` picks it up.

Validation is **auto**: the Critic stamps. The Conductor merges as soon as the verdict is `APPROVED` and the CI is green, and escalates otherwise.
