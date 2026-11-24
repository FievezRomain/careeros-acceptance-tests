@BR-JOB-002 @BR-JOB-003 @BR-JOB-004 @BR-JOB-005 @BR-JOB-006 @BR-JOB-007
Feature: Discover owned opportunities every day without repeated processing
  Active search snapshots are collected through supported structured sources while
  provenance, immutable versions and downstream eligibility remain explicit.

  Scenario: Only eligible active searches run once in their daily window
    Given active, paused and out-of-window synthetic search snapshots
    When the scheduled discovery command is replayed
    Then only eligible active snapshots are collected once for that local day
    And identical normalized signatures share retrieval without weakening criteria

  Scenario: Every structured result is observed incrementally
    Given a structured source with several result pages
    When daily discovery consumes the source
    Then every page is consumed or explicit truncation evidence is recorded
    And cursor, conditional-request and rate-limit metadata remain observable

  Scenario: Rediscovery preserves provenance and immutable versions
    Given a source opportunity has already been discovered
    When unchanged and materially changed observations arrive
    Then unchanged content updates last seen time without downstream work
    And changed content creates a new immutable version with source provenance

  Scenario: Only actionable new versions can continue to notification matching
    Given new, duplicate, ignored and expired synthetic opportunities
    When discovery classifies downstream work
    Then only new actionable versions emit a matching candidate
    And source-stated, inferred and unknown fields remain distinguishable
