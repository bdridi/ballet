---
name: hybrid-track
description: Piece v0. The Director has framed the work with the Dramaturg (interactive Workshop); this launches the Rehearsal of one issue in auto with the Conductor (plan if missing, code, validation) up to the Premiere, unless it escalates. Use as `/ballet:hybrid-track #<issue>`, from the project's home folder, once the issue exists.
---

# hybrid-track

The Director's call to this Piece is their Workshop stamp: from here, the Rehearsal runs in auto.

1. Take the issue number from the arguments (`#12` or `12`). None: ask the Director which issue, and stop.
2. Load the skill `/ballet:conductor` and follow it, beginning with `begin <issue>`.

Validation is **auto**: the Critic stamps. The Conductor merges as soon as the verdict is `APPROVED` and the CI is green, and escalates otherwise.
