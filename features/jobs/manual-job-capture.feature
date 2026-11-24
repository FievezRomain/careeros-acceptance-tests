@BR-ACC-001 @BR-ACC-002 @BR-JOB-001 @BR-JOB-002
Feature: Record an owned opportunity from a manual source
  A signed-in person can preserve the source wording and provenance of an opportunity
  without choosing or seeing another account's ownership identifiers.

  Scenario: A manual opportunity preserves its source and provenance
    Given a signed-in synthetic person
    When the person records a title, employer, description, source reference and raw source wording
    Then the opportunity is owned by that person
    And its source is identified as manual
    And the source reference, capture time and raw wording are preserved
    And retrying the same command does not create a duplicate opportunity

  Scenario: Invalid, unauthenticated and forged-owner submissions are refused
    Given the manual opportunity endpoint
    When a request is missing a required opportunity field
    Then the request is rejected as invalid
    When a request has no signed-in person
    Then the request is rejected as unauthenticated
    When a signed-in person supplies an ownership identifier in the request body
    Then the request is rejected without assigning the opportunity to that identifier
