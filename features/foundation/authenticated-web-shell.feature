@BR-ACC-001
Feature: Protect the CareerOS web workspace
  The public sign-in entry is available to everyone, while the application shell is rendered
  only after a browser session has been restored successfully.

  Scenario: Anonymous and invalid sessions cannot open the application shell
    Given the CareerOS web application is available
    When a visitor opens a protected workspace route without a valid session
    Then the visitor is redirected to sign in
    And no private workspace content or token is disclosed

  Scenario: A signed-in person can navigate inside the protected shell
    Given a synthetic person has a valid browser session
    When the person opens the protected workspace
    Then the application shell and its primary navigation are displayed
    And the response prevents browser caching of private content
