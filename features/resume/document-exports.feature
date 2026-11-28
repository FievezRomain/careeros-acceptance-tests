Feature: Owned, text-extractable resume exports

  @BR-RES-007 @BR-RES-008 @BR-RES-009
  Scenario: Export a grounded resume as PDF and DOCX
    Given an owned immutable profile snapshot with confirmed resume content
    And its source response includes a hidden prompt, an internal score and a private annotation
    When the owner requests both formats and retries the same export
    Then a single immutable version records both artifact checksums
    And the final downloadable PDF and DOCX expose the same confirmed text in reading order
    And the file contents and metadata exclude internal and unconfirmed material

  @BR-ACC-002 @BR-RES-009
  Scenario: Access and integrity are checked on download
    Given the service registered a version with both formats
    Then another account or tenant cannot obtain the documents
    And a damaged stored artifact is withheld

  @BR-RES-008 @BR-RES-009
  Scenario: Retry after a storage interruption
    Given storage interrupts the second artifact write
    When the owner retries with the original idempotency key
    Then the service completes one new version containing both artifacts
