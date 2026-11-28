Feature: Compare the final resume with source-quoted offer requirements

  @BR-ATS-001 @BR-ATS-002 @BR-ATS-003 @BR-ATS-006 @BR-ATS-007 @BR-ATS-008 @BR-ACC-002
  Scenario: Trace each term to the exact offer and final file
    Given an owner has a final export and an owned recommendation with source-quoted requirements
    When they request relevance for the exact offer version
    Then the report identifies the export, offer and requirement evidence versions
    And it locates the matching wording in the file and identifies a term with no located mention
    And technical structure and employer decisions remain separate from these findings
    And another tenant cannot access the report

  @BR-ATS-005 @BR-ATS-008
  Scenario: Report the limits of the comparison
    Given the file is unreadable, the offer is link-only, or its source version has changed
    When the owner requests relevance
    Then the result explains why the comparison is inconclusive
