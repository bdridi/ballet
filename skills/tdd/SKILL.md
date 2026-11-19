---
name: tdd
description: Common TDD rule. Load it before writing code: a failing test first, then the minimal code, then the refactoring.
---

# TDD

1. Write a failing test, for a single behaviour.
2. Write the minimal code that makes it pass.
3. Refactor, with the tests green.

No production code without a test that asked for it. A test depends neither on execution order nor on another test.

## Mutation

When the project declares a mutation tool, Ballet runs it on the lines the branch changed, after the proof. A surviving mutant is a behaviour no test pins down:

- **Kill a survivor with a unit test**, never an end-to-end test: the smallest test that fails on the mutant and passes on the code.
- **An equivalent mutant** (no test can tell it from the code: same observable behaviour) is excluded in the tool's own config file (`config` of its entry in the profile), with its reason written next to it. Never exclude a survivor to save writing a test.
- **The Critic judges each exclusion** added on the branch: a reason that does not hold, or a mutant a test could kill, is a blocking point.
