Feature: Owned job catalog and match explanations

  @BR-JOB-002 @BR-JOB-006 @BR-MAT-001 @BR-MAT-002 @BR-MAT-003 @BR-MAT-004 @BR-MAT-005 @BR-MAT-006 @BR-MAT-008
  Scenario: Browse ranked opportunities and inspect the matching evidence
    Given the signed-in person has verified and external-to-verify opportunities
    When they open Jobs, browse the catalog and inspect a recommendation
    Then the recommendations retain their service ordering
    And the detail shows the evaluated opportunity version and its source
    And the score explanation shows requirement findings, uncertainty, hard conflicts and the score limitation
    And a link awaiting verification has no assessable score

  @BR-ACC-002 @BR-MAT-001
  Scenario: Deny access and withhold evidence for a different opportunity version
    Given a job detail is requested with a denied credential or a mismatched match version
    Then denied requests disclose no opportunity content
    And an authorized detail with a mismatched match never renders the other version's evidence
