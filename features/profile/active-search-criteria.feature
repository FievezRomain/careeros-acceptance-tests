@BR-PRO-008 @BR-PRO-009 @BR-PRO-010 @BR-ACC-002
Feature: Configure an owned daily opportunity search
  A signed-in person controls an explicit daily search whose immutable criteria
  can drive provider-neutral discovery without disclosing private profile facts.

  Scenario: Activate and version explicit search criteria
    Given a signed-in synthetic profile owner
    When the person activates a search with roles, locations, work preferences and exclusions
    Then the active state, timezone, daily window and criteria version are visible
    And a material criteria change preserves the previous immutable version

  Scenario: Pause and resume only the owned search
    Given an active owned search
    When the owner pauses and resumes automatic discovery
    Then the current state reflects the requested transition
    And anonymous and differently owned access disclose no criteria

  Scenario: Publish only a minimal exact retrieval signature
    Given two people with exactly equivalent normalized search dimensions
    When discovery requests their provider-neutral signatures
    Then the signatures are identical without contact data or raw profile facts
    And their individual thresholds remain separate and are never averaged

  Scenario: Request rematching only for relevant changes
    Given a versioned active search
    When profile and criteria changes are classified
    Then role, skill, experience, location, work-preference and criteria changes request rematching
    And contact-only and presentation-only changes do not request rematching
