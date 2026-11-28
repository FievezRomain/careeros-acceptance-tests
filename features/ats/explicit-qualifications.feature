Feature: Check explicit qualification minima before application

  @BR-MAT-010 @BR-MAT-003 @BR-MAT-004
  Scenario: Matching evaluates an offer minimum on the same scale as a confirmed fact
    Given the opportunity requires five years of Python, English B2, and SQL level 4 out of 5
    When the confirmed profile shows two years of Python, no verified English level, and SQL level 4
    Then Matching finds a hard conflict for Python and leaves English unassessed
    And the SQL minimum is satisfied

  @BR-ATS-009 @BR-ATS-006 @BR-ACC-002
  Scenario: Report an explicit shortfall for the exact export, offer and profile
    Given an owned final export and Matching evidence for its offer and profile snapshot
    When the owner requests the ATS relevance report
    Then a confirmed mandatory shortfall is marked as an error
    And optional shortfalls and unknown qualifications are warnings
    And a stale profile or offer cannot produce an eligibility error
