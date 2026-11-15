# FEAT-NNN — Feature name

- **Status**: draft | ready
- **Capability**: CAP-NNN
- **Answers**: OPP-NNN (optional)
- **Depends on**: FEAT-NNN (optional)

## Problem

For whom, and what it costs today. One or two sentences taken from the opportunity or the capability.

## Proposal

What the product will do, coarse-grained. A `draft` feature may stop here.

## Journey

What the person sees and does, step by step, in business language: empty state, loading, error. Product copy is quoted verbatim, in the product's language. Absent if the feature has no screen.

## Rules

Invariants, refusals and edge cases settled during the Workshop. The capability's rules are not copied here: they become criteria.

## Acceptance criteria

Four at most: beyond that, the feature is too big and gets re-cut. Checkable scenarios, tagged `@FEAT-NNN-C1`: the same tag appears on the tests that cover them. Never renumber, append at the end. Progress is not written here.

```gherkin
@FEAT-NNN-C1
Scenario: alice …
  Given …
  When …
  Then …
```

## Out of scope

Mandatory: what the feature does not do, and where it is handled, if anywhere.

## Open questions

- [ ] …
