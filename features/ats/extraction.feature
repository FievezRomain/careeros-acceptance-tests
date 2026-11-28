Feature: Extract text from the final owned resume export

  @BR-ATS-001 @BR-ACC-002
  Scenario: Extract the PDF and DOCX attached to a specific resume version
    Given an owner can read two immutable resume versions with distinct synthetic content
    When they ask ATS to extract a particular version and format
    Then the text and content digest come from that final artifact
    And sessions outside the owner or tenant cannot read its content

  @BR-ATS-005
  Scenario: Produce an inconclusive result for non-extractable content
    Given the final artifact is empty or unreadable
    When the owner asks ATS to extract its text
    Then the response has an inconclusive status and a reason without text or a score
