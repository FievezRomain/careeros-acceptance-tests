@BR-JOB-003 @BR-JOB-004 @BR-JOB-006
Feature: Normalize and query an owned opportunity catalog
  A signed-in person sees one current catalog entry for repeated discoveries while
  material source changes remain versioned and source certainty stays explicit.

  Scenario: Repeated discoveries are normalized and grouped
    Given a signed-in synthetic person
    When equivalent role and employer wording is captured more than once
    Then the catalog contains one normalized current opportunity
    And the person can explicitly keep a discovery in a separate group

  Scenario: A material change creates a new immutable version
    Given a normalized opportunity already exists
    When the same role and employer are captured with materially changed source wording
    Then the current opportunity has a new version in the same group
    And the previous version remains queryable without being overwritten

  Scenario: Query results preserve certainty and ownership
    Given opportunities owned by two synthetic people
    When one person queries their catalog
    Then only that person's current opportunities are returned
    And source-stated, inferred and unknown fields remain distinguishable
