@BR-ACC-002 @BR-PRO-001 @BR-PRO-004 @BR-PRO-005
Feature: Maintain an owned professional profile
  A signed-in person can manage structured experience, education and skill facts without
  exposing them to another account or misrepresenting self-declared information.

  Scenario: The owner creates, reads, updates and removes profile items
    Given a signed-in synthetic person with an empty profile
    When the person adds an experience, an education item and a self-declared skill
    Then all three items are visible in that person's profile
    And the skill level is identified as self-declared
    When the person updates the experience and removes the education item
    Then the updated experience is returned
    And the removed education item is no longer returned

  Scenario: Invalid dates and cross-account access are refused
    Given two distinct signed-in synthetic people
    When the first person submits an experience whose end date precedes its start date
    Then the experience is rejected as invalid
    When the second person requests or changes the first person's profile item
    Then access is refused without revealing whether that item exists
