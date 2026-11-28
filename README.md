# CareerOS Acceptance Tests

Executable business acceptance and cross-service non-regression tests for CareerOS.

The business-rule source of truth lives in [`careeros-workspace/docs/business-rules`](https://github.com/FievezRomain/careeros-workspace/tree/main/docs/business-rules). This repository contains black-box scenarios that prove those rules through supported product boundaries. It never reads a service database directly.

## What this repository answers

- Which business rules have an executable scenario?
- Which scenario failed after a change?
- Can the complete V1 journey still be completed?
- Are rules being changed without corresponding acceptance coverage?

## Commands

When this repository is used as the `acceptance-tests` workspace submodule:

```powershell
npm test
npm run coverage:no-new-gaps
npm run coverage:full
```

`npm test` validates the harness and existing traceability. `npm run coverage:no-new-gaps` is the continuous merge gate: the initial uncovered-rule baseline can only shrink, so every newly introduced business rule must arrive with an acceptance scenario in this repository. `npm run coverage:full` is the V1 release gate: it fails until every active catalog rule has at least one executable scenario.

The workspace runs the no-new-gaps command against its canonical catalog and the exact `acceptance-tests` submodule revision. Adding a rule therefore requires updating this repository first, then updating the workspace submodule pointer.

For a standalone clone, set `CAREEROS_RULES_CATALOG` to the absolute path of the workspace catalog.

`npm run test:open-web` runs the V1-057 HTTP scenarios in the workspace. Install
the locked development environments in `services/ai-gateway` and `services/job-service`
first. The runner starts both apps on ephemeral loopback ports with synthetic
provider responses, synthetic identities and an isolated SQLite catalog.

`npm run test:matching` checks the matching HTTP contract against synthetic profiles
and opportunities. Install the locked development environment in `services/matching-service`.
`npm run test:extraction` verifies source-grounded extraction across the same HTTP
boundary using synthetic gateway replies and no live credentials.
`npm run test:recommendations` exercises projection delivery, score history and the
recommendation outbox through HTTP with synthetic identities and a disposable SQLite database.

`npm run test:job-match-ui` exercises the protected React routes for V1-026 with
synthetic service responses. Run `npm ci` in `apps/web` first.

`npm run test:resume-versions` exercises V1-027 through the resume HTTP API.
Install the locked development environment in `services/resume-service` first.

`npm run test:resume-drafts` exercises V1-028 through the resume HTTP API
with synthetic responses from the versioned profile and job APIs.

`npm run test:resume-exports` renders and downloads both final file formats,
then extracts their text through the V1-029 HTTP boundary.

`npm run test:recommendation-resume` exercises pinned generation, preview,
explicit approval and stale-profile detection for V1-059.

`npm run test:ats-extraction` exercises V1-030 through the ATS HTTP API with
synthetic final exports. Install the locked environment in `services/ats-service` first.

## Safety

Fixtures are fictitious. Real message and application delivery is disabled. Provider sandboxes require separate configuration and explicit approval.

## License

Apache-2.0.
