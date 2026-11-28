Feature: Grounded resume drafts

  @BR-RES-001 @BR-RES-002 @BR-RES-003
  Scenario: Build a targeted draft from the selected profile snapshot
    Given an owned snapshot with confirmed experience and skill facts and an unconfirmed suggestion
    And an owned opportunity version with verified full text
    When the owner generates a targeted draft
    Then the draft pins both versions and identifies every included source fact
    And the draft preserves confirmed values and excludes unconfirmed claims

  @BR-RES-001 @BR-RES-002 @BR-RES-003 @BR-JOB-006 @BR-ACC-002
  Scenario: Reject unsupported claims and inaccessible draft sources
    Given a draft request identifies a confirmed fact, an unconfirmed one or an inaccessible source
    Then only the confirmed selection can produce draft content
    And caller-supplied claims, another owner's snapshot and a link awaiting verification are rejected
