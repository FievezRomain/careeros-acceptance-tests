# Agent instructions — careeros-acceptance-tests

Read README.md, docs/overview.md and the central workspace business-rule catalog before changing this repository.

## Required invariants

- Test behavior only through public user-facing or service contracts; never query service databases directly.
- Every scenario must reference at least one existing `BR-<DOMAIN>-NNN` rule.
- Every new business rule must be accompanied by an acceptance scenario in this repository; never add a new rule to the frozen uncovered-rule baseline.
- When a previously uncovered rule gains a scenario, remove its identifier from `config/coverage-baseline.json` in the same change.
- A scenario proves behavior only when its assertions execute; prose-only scenarios do not count as covered.
- Use synthetic identities, job offers, resumes and messages. Never add personal data or credentials.
- Do not send real applications, emails, WhatsApp messages or other external communications.
- Keep provider-specific setup behind adapters and make costs or unavailable providers explicit.
- A failing business-rule scenario is a release failure, not a snapshot to update automatically.
