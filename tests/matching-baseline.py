"""Black-box scoring acceptance through the matching service HTTP boundary."""

from uuid import UUID

from fastapi.testclient import TestClient

from careeros_matching.adapters.http import Settings, create_app
from careeros_matching.application.scoring import Actor


def uid(n):
    return str(UUID(int=n))


class FixtureVerifier:
    def verify(self, token):
        assert token == 'fixture-actor'
        return Actor(account_id=UUID(int=1), tenant_id=UUID(int=2), scopes=('matching:score',))


def command():
    owner = {'accountId': uid(1), 'tenantId': uid(2)}
    return {
        'profile': {**owner, 'snapshotId': uid(3), 'confirmedFacts': [
            {'factId': uid(11), 'key': 'python', 'level': 5},
            {'factId': uid(12), 'key': 'sql', 'level': 2},
            {'factId': uid(13), 'key': 'kubernetes', 'level': 0},
        ]},
        'opportunity': {**owner, 'versionId': uid(4), 'sourceAccess': 'full_text', 'requirements': [
            {'requirementId': uid(21), 'key': 'Python', 'minimumLevel': 4, 'mandatory': True,
             'statement': 'Python level 4'},
            {'requirementId': uid(22), 'key': 'sql', 'minimumLevel': 4, 'mandatory': True,
             'statement': 'SQL level 4'},
            {'requirementId': uid(23), 'key': 'kubernetes', 'minimumLevel': 2, 'mandatory': True,
             'hardEligibility': True, 'statement': 'Kubernetes is an eligibility requirement'},
            {'requirementId': uid(24), 'key': 'redis', 'minimumLevel': 2, 'mandatory': False,
             'statement': 'Redis optional'},
            {'requirementId': uid(25), 'key': 'python', 'minimumLevel': 5, 'mandatory': False,
             'statement': 'Python level 5 preferred'},
        ]},
    }


settings = Settings(oidc_issuer='https://identity.example.invalid', oidc_audience='fixture',
                    oidc_jwks_url='https://identity.example.invalid/jwks')
with TestClient(create_app(settings, FixtureVerifier())) as app:
    def post(payload):
        return app.post('/v1/internal/matches/score', json=payload,
                        headers={'Authorization': 'Bearer fixture-actor'})

    pair = command()
    response = post(pair)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result == post(pair).json()
    assert result['profileSnapshotId'] == uid(3)
    assert result['opportunityVersionId'] == uid(4)
    assert result['scorerVersion'] == 'baseline-v1'
    assert result['score'] == 57  # (2 + 1 + 0 + 1) / (2 + 2 + 2 + 1), rounded
    assert result['explanation'] == {
        'version': 'evidence-v1', 'assessedRequirements': 4, 'totalRequirements': 5,
        'assessedWeight': 7, 'totalWeight': 8, 'earnedWeight': 4.0,
        'uncertainty': 'unconfirmed_profile_facts', 'scoreBounds': {'minimum': 50, 'maximum': 63},
    }
    findings = {finding['requirementId']: finding for finding in result['findings']}
    for requirement, status, fact, level, earned in zip(
        pair['opportunity']['requirements'],
        ('satisfied', 'partial', 'missing', 'unknown', 'satisfied'), (11, 12, 13, None, 11),
        (5, 2, 0, None, 5), (2.0, 1.0, 0.0, None, 1.0),
        strict=True,
    ):
        finding = findings[requirement['requirementId']]
        assert finding['status'] == status
        assert finding['statement'] == requirement['statement']
        assert finding['factId'] == (uid(fact) if fact is not None else None)
        assert finding['minimumLevel'] == requirement['minimumLevel']
        assert finding['confirmedLevel'] == level
        assert finding['weight'] == (2 if requirement['mandatory'] else 1)
        assert finding['earnedWeight'] == earned
        assert finding['hardEligibility'] == requirement.get('hardEligibility', False)
    assert result['hardConflicts'] == [uid(23)]
    assert result['limitation'] == 'This score supports prioritization and does not guarantee an interview or employment.'

    pair['profile']['confirmedFacts'] = []
    unknown = post(pair).json()
    assert unknown['score'] is None and unknown['hardConflicts'] == []
    assert unknown['explanation']['assessedWeight'] == 0
    assert unknown['explanation']['scoreBounds'] == {'minimum': 0, 'maximum': 100}
    assert all(finding['earnedWeight'] is None for finding in unknown['findings'])

    pair['opportunity']['requirements'] = []
    no_requirements = post(pair).json()
    assert no_requirements['explanation']['uncertainty'] == 'no_verified_requirements'
    assert no_requirements['explanation']['scoreBounds'] is None
    pair['opportunity'].update(sourceAccess='external_to_verify', requirements=[])
    partial = post(pair).json()
    assert partial['sourceAccess'] == 'external_to_verify'
    assert partial['score'] is None and partial['findings'] == []
    assert partial['explanation']['uncertainty'] == 'external_to_verify'
    assert partial['explanation']['scoreBounds'] is None
    for snapshot, field in (('profile', 'accountId'), ('opportunity', 'tenantId')):
        foreign = command()
        foreign[snapshot][field] = uid(99)
        denied = post(foreign)
        assert denied.status_code == 404 and denied.json()['code'] == 'SNAPSHOT_NOT_FOUND'

    qualified = command()
    qualified['profile']['confirmedFacts'] = [
        {'factId': uid(11), 'key': 'python', 'level': 5, 'experienceMonths': 24},
        {'factId': uid(12), 'key': 'english', 'level': 3},
        {'factId': uid(13), 'key': 'sql', 'level': 4},
        {'factId': uid(14), 'key': 'French', 'level': 4, 'cefr': 'B1'},
    ]
    qualified['opportunity']['requirements'] = [
        {'requirementId': uid(21), 'key': 'Python', 'minimumLevel': 1, 'mandatory': True,
         'statement': 'Python: at least 5 years of experience'},
        {'requirementId': uid(22), 'key': 'English', 'minimumLevel': 1, 'mandatory': True,
         'statement': 'English B2 required'},
        {'requirementId': uid(23), 'key': 'SQL', 'minimumLevel': 1, 'mandatory': True,
         'statement': 'SQL level 4/5'},
        {'requirementId': uid(24), 'key': 'French', 'minimumLevel': 1, 'mandatory': False,
         'statement': 'French B2 preferred'},
        {'requirementId': uid(25), 'key': 'Python', 'minimumLevel': 1, 'mandatory': True,
         'statement': 'Python: 2 to 5 years'},
    ]
    result = post(qualified)
    assert result.status_code == 200, result.text
    result = result.json()
    findings = {finding['requirementId']: finding for finding in result['findings']}
    assert result['qualificationPolicy'] == 'explicit-requirements-v1'
    assert result['hardConflicts'] == [uid(21)]
    assert findings[uid(21)]['qualification'] == {
        'unit': 'experience_months', 'required': 60, 'confirmed': 24, 'status': 'not_met',
    }
    assert findings[uid(22)]['status'] == 'unknown'
    assert findings[uid(22)]['qualification']['confirmed'] is None
    assert findings[uid(23)]['qualification']['status'] == 'met'
    assert findings[uid(24)]['qualification']['status'] == 'not_met'
    assert not findings[uid(24)]['hardEligibility']
    assert 'qualification' not in findings[uid(25)]

print('V1-023 and V1-025 HTTP acceptance passed for BR-MAT-001 through BR-MAT-006.')
print('Matching explicit minima HTTP acceptance passed for BR-MAT-010.')
