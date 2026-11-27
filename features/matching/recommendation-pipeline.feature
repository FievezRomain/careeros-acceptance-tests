Feature: Recommendations follow owned opportunity and criteria versions

  @BR-MAT-001 @BR-MAT-002 @BR-MAT-003 @BR-MAT-004 @BR-MAT-005 @BR-MAT-006 @BR-MAT-008 @BR-MAT-009 @BR-JOB-004 @BR-JOB-005 @BR-JOB-007
  Scenario: Individual decisions and retry-safe notification intent
    Given two owned searches and an immutable synthetic opportunity available to both
    When the same opportunity version is projected for both accounts and redelivered
    Then extraction is shared and each account gets its own score and listing decision
    And a qualifying account receives a single recommendation-created event
    When a relevant profile revision, a contact change and an ignore transition arrive
    Then the listing changes only for relevant inputs and an ignored job is no longer actionable
    And historical evidence, uncertainty and the score limitation are available only to the owner

  @BR-MAT-007 @BR-MAT-004
  Scenario: Correct evidence without rewriting an evaluation
    Given an owned result and its verified source
    When the owner corrects a requirement and a link-only result is discovered
    Then the correction adds a new evaluation and keeps the earlier one readable
    And the link-only result retains unknown requirements without a score
