# Configuration

Two files, both yours to edit:

| File | Scope |
|---|---|
| `.ballet/config.toml` in a project | the project profile (created by `/ballet:init-project`) |
| `~/.ballet/maestro.toml` | the machine: projects, limits, Maestro, Conductors, capacity (see [Maestro](maestro.md)) |

Every key is optional. The defaults are in the plugin's [`config.toml`](../config.toml), and a project overrides them key by key.

To check a project's configuration by hand:

```sh
python3 <path-to-ballet>/scripts/ballet_config.py check <project-folder>
```

## A project profile

```toml
[roles.dancer]                  # which CLI and model plays each role
cli = "claude"
model = "sonnet"                # the Critic must differ from the Dancer: another CLI, or another model

[conductor]
model = "sonnet"                # optional: the model of this project's Conductors; without it, `[conductors] model`
                                # of ~/.ballet/maestro.toml for the whole machine, else haiku (it only relays scripts)

[rehearsal]
plan_approval = true            # assisted: the plan waits for you (the issue's `Plan approval` field wins)

[workshop]
queue_approval_skipped = []     # work types a Workshop publishes `ready` instead of `proposed` ("Bug", "Task", "Feature")

[escalation]
max_round_trips = 2             # Dancer ↔ Critic round trips before it comes to you
max_exchange_rounds = 3         # question rounds between two roles on one subject
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

## GitHub issue types and fields

`/ballet:init-project` creates, for the repo's owner (your account or your organization, shared by all its repos), only what is missing:

- the issue type `Slice`, next to `Task`, `Bug` and `Feature`;
- five issue fields: `Ballet status` (`proposed`, `ready`, `in-rehearsal`, `plan-review`, `escalated`, `done`), `Rehearsal mode` (`assisted`, `autopilot`), `Size` (`S`, `M`), `Plan approval` (`required`, `skipped`) and `Priority`.

A field that exists without all its options is reported: complete it in Settings → Planning. To redo this step by hand, e.g. for a project whose remote did not exist yet:

```sh
python3 <path-to-ballet>/scripts/ballet_planning.py <project-folder>
```

## Languages

Code is always in English. Specs are in English by default (`[project] specs_language` to change it, e.g. for a client who reads them). Text the product displays stays in the product's language: scenarios quote it verbatim, and the glossary maps each term to its code name and its UI wording. The rule is in the `ballet:ddd` skill.
