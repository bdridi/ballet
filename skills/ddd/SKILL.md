---
name: ddd
description: Common DDD rule. Load it to name and structure code after the business domain (ubiquitous language, invariants, bounded contexts).
---

# DDD

- Use the domain language in the specs, the tests and the code. The project glossary is the authority.
- Domain invariants live in the model, not in the technical layers.
- A business notion has one name and one place where it is defined.
- Respect bounded contexts: no model leaks into another.

## Language

- **Code is in English.** Always.
- **Specs are in the specs language**: `[project] specs_language` in `.ballet/config.toml`, English by default. In English, a domain term and its code name are the same word: nothing to translate.
- **Product copy stays in the product's language.** A criterion is checked by looking at the product, which displays its text in its own language: Gherkin quotes that text verbatim (`Then she sees « Voir ma trajectoire »`). The link between a criterion and its test is the tag (`@FEAT-NNN-Cn`), never the text of the scenario.
- **The glossary is the only mapping.** A term enters it with its definition, its code name and its UI wording at the same time. The code uses no domain name that is not in it. A renaming happens in the glossary first, then in the code.
- A notion with no equivalent in English (a local legal status, a national savings product) keeps its original name, as a loanword, in the glossary and in the code.
