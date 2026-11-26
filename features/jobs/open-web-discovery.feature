Feature: Discover opportunities through open-web results

  @BR-JOB-002 @BR-JOB-003 @BR-JOB-004 @BR-JOB-006
  Scenario: Retain a link with partial evidence and version its later resolution
    Given an active synthetic search with two distinct opportunities sharing a title
    And the search provider returns duplicates and an unresolved external job link
    When daily discovery runs and the owner reads the job catalog
    Then each distinct opportunity appears once with its source reference
    And the external link has explicit unknown fields and is ineligible for resume generation
    When a later run verifies a canonical full-text source for the external link
    Then the existing opportunity group gets a new version with complete source access
    And the original version remains readable under its original evidence state

  @BR-AI-002
  Scenario: An untrusted search result is excluded
    Given a search provider fixture containing usable links and an invalid URL
    When an authorized service invokes the gateway discovery capability
    Then only validated results with source evidence are returned
