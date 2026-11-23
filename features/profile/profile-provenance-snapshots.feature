@BR-PRO-002 @BR-PRO-003 @BR-PRO-006
Feature: Preserve profile-fact provenance and immutable snapshots
  Profile facts retain their origin and confirmation status, while approved downstream
  artifacts can keep using an immutable view after the live profile changes.

  Scenario: Imported and generated facts require explicit confirmation
    Given a signed-in synthetic person with an empty profile
    When an imported fact and a generated suggestion are added to the profile
    Then both facts record their origin and remain unconfirmed
    When the person explicitly confirms the imported fact
    Then that fact is user-confirmed

  Scenario: A live correction does not rewrite an existing snapshot
    Given a signed-in synthetic person with a confirmed imported fact
    When the person creates a profile snapshot and later corrects the live fact
    Then the live fact records a user correction
    And the snapshot still contains the confirmed imported fact as originally captured
    And another signed-in person cannot read that snapshot
