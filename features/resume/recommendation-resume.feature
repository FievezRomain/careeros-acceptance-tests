Feature: Create and approve a resume from a recommendation

  @BR-PRO-007 @BR-RES-001 @BR-RES-002 @BR-RES-003 @BR-RES-007 @BR-RES-010
  Scenario: Tailor a version to a pinned qualifying recommendation
    Given an owned evaluation with a supported requirement and a missing requirement
    When the person creates a resume from that evaluation
    Then the exported text uses only the matched confirmed fact
    And the review reports the missing requirement and identifies the source versions
    And retrying the same command returns the same version

  @BR-PRO-006 @BR-RES-004 @BR-RES-005 @BR-RES-006 @BR-RES-010
  Scenario: Approve an exact preview and preserve its history when facts change
    Given the owner previews a generated version
    When the owner explicitly approves it and then corrects a referenced profile fact
    Then the original approval and exported content are preserved
    And the original version becomes ineligible for a package
    And generation from the refreshed evaluation creates a distinct version

  @BR-ACC-002 @BR-JOB-006 @BR-RES-010
  Scenario: Reject other owners, mismatched pins and link-only offers
    Given the request refers to an inaccessible, stale or link-only recommendation
    Then the request cannot produce an export or approval
