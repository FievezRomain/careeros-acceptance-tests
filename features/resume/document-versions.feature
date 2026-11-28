Feature: Immutable resume versions

  @BR-RES-008
  Scenario: Register and inspect immutable version provenance and artifact metadata
    Given an owner registers a PDF version with its profile and opportunity references
    When the owner retries the registration and registers a new DOCX version
    Then the retry returns the first version
    And both versions retain their original references and metadata in order

  @BR-RES-008 @BR-ACC-002
  Scenario: Reject invalid or unauthorized access without changing the history
    Given a first version already exists
    Then conflicting registration retries and malformed artifact metadata are rejected
    And another account or tenant cannot read the owner's version
    And the history contains only the registered versions
