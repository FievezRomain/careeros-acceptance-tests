# Executable business conformance

## Separation of responsibilities

The workspace catalog states the business rules in plain language. This repository proves observable behavior. Individual services retain their own unit, integration and contract tests.

Acceptance scenarios:

1. start from a synthetic user situation;
2. interact only through supported public boundaries;
3. assert a business-visible outcome;
4. reference every rule they prove using an `@BR-...` tag;
5. leave the test environment repeatable and free of real external delivery.

## Traceability gate

The traceability command reads the canonical catalog, extracts active rule identifiers and compares them with scenario tags. It rejects unknown identifiers immediately. Release mode additionally rejects any active rule without a scenario.

A tagged prose scenario is not sufficient for final coverage. Future feature stories add executable step definitions and mark scenarios executable only after their assertions run successfully.

## Planned layers

- domain acceptance: one bounded behavior and its denial paths;
- cross-service journeys: a rule spanning multiple services;
- V1 journey: authenticate, build a profile, capture a job, match, generate and assess a resume, approve an application, track progress and observe analytics;
- channel adapters: fake delivery by default, provider sandbox only in separately approved jobs.

## Environment policy

The same scenario suite can target a local stack or an isolated review environment. Environment configuration selects endpoints and test adapters; it cannot weaken ownership checks, approvals or business assertions.
