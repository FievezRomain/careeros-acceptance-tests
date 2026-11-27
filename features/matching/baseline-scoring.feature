Feature: Score one confirmed profile and one job version deterministically

  @BR-MAT-001 @BR-MAT-002 @BR-MAT-003 @BR-MAT-004 @BR-MAT-005 @BR-MAT-006
  Scenario: Known requirements contribute according to weight and evidence
    Given a confirmed synthetic profile snapshot and an owned opportunity version
    When the caller scores the pair twice
    Then both results are identical and name the same input versions
    And satisfied, partial, missing and unknown findings retain their evidence
    And unresolved requirements do not enter the denominator
    And a confirmed eligibility conflict and the prioritization limitation are visible

  @BR-MAT-001 @BR-MAT-004
  Scenario: Link-only and foreign snapshots cannot be scored as confirmed evidence
    Given an opportunity link awaiting verification
    Then the score is unknown
    And the scoring boundary denies either input owned by another account or tenant
