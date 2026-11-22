@BR-ACC-001 @BR-ACC-002
Feature: Protect a person's CareerOS workspace
  A person must sign in and must never see another person's career information.

  Scenario: An anonymous visitor cannot open a private workspace
    Given a private CareerOS workspace exists for a synthetic person
    When an anonymous visitor tries to open that workspace
    Then access is refused
    And no profile, opportunity, resume or application detail is disclosed

  Scenario: One signed-in person cannot open another person's workspace
    Given two distinct synthetic CareerOS accounts
    When the first person requests the second person's workspace
    Then access is refused
    And the refusal does not reveal whether a requested private record exists

@BR-RES-001 @BR-RES-002 @BR-AI-005
Feature: Keep generated resumes grounded
  Generated content must remain based on confirmed facts and under human control.

  Scenario: Missing experience is not invented
    Given a confirmed profile without management experience
    And a job opportunity requesting management experience
    When a resume is generated for that opportunity
    Then the resume does not claim management experience
    And the missing requirement remains visible to the person

@BR-COM-001 @BR-COM-002 @BR-COM-006
Feature: Require approval before external communication
  CareerOS can prepare useful drafts without contacting third parties on its own.

  Scenario: A due follow-up creates a draft only
    Given a submitted application whose follow-up is due
    When the follow-up workflow runs
    Then a message draft is available for preview
    And no external message is delivered before the person approves that exact draft
