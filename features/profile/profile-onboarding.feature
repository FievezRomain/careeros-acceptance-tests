@BR-ACC-002 @BR-PRO-001 @BR-PRO-004 @BR-PRO-005
Feature: Build and edit a professional profile from the protected web workspace
  A signed-in person can load, create and correct owned profile facts while invalid input and
  insufficient authorization fail without exposing another person's data.

  Scenario: An owner completes profile onboarding and corrects an experience
    Given a signed-in synthetic person opens an empty profile workspace
    When the person adds an experience, education item and self-declared skill
    Then the saved facts are displayed only in that person's profile
    When the person corrects the experience
    Then the corrected value is displayed with user-confirmed status

  Scenario: Validation and authorization failures remain safe and actionable
    Given a signed-in synthetic person opens the profile editor
    When the person enters an end date before the start date
    Then the editor rejects the invalid date range without sending it
    When the person's session lacks profile access
    Then the editor displays an authorization error without profile facts or token details
