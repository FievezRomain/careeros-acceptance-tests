Feature: Extract requirements from an immutable opportunity version

  @BR-MAT-003 @BR-AI-002
  Scenario: Keep only evidence grounded in the source version
    Given an owned synthetic opportunity and a gateway result with grounded and invented claims
    When the caller requests extraction for that opportunity version
    Then only the requirement with a matching source excerpt is returned as a suggestion
    And the result identifies the opportunity, extractor, model and prompt versions
    And a result with no grounded requirement is marked inconclusive

  @BR-MAT-004 @BR-ACC-002
  Scenario: Prevent extraction without an owned full-text opportunity
    Given a link-only opportunity and a full-text version owned by a different account
    When the caller requests extraction for either opportunity
    Then the link remains unassessed and the other account's version is unavailable
    And the extraction gateway receives neither request
