Feature: Assess the structure of a final resume artifact

  @BR-ATS-001 @BR-ATS-003 @BR-ATS-004 @BR-ATS-006 @BR-ACC-002
  Scenario: Explain the versioned CareerOS score for the exact owned artifact
    Given two final exports differ in the presence of an experience date
    When the owner requests a structural report for each export
    Then each report identifies its artifact and rubric version
    And the missing date identifies the affected line and a suggested correction
    And checks that do not apply are excluded from the score denominator
    And another account cannot read the report

  @BR-ATS-005
  Scenario: Report inconclusive when the final export has no readable text
    Given the final PDF has no extractable text
    When the owner requests a structural report
    Then the report identifies the artifact and reason without a technical score
