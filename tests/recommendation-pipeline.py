"""V1-058 acceptance against the matching HTTP API and its SQL adapter."""

from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from careeros_matching.adapters.http import Settings, create_app
from careeros_matching.adapters.postgresql.migrations.runner import SqlMigrations
from careeros_matching.adapters.postgresql.store import SqlRecommendationStore
from careeros_matching.application.extraction import Candidate, GatewayExtraction, Provenance
from careeros_matching.application.scoring import Actor


def uid(number):
    return str(UUID(int=number))


class Identity:
    def verify(self, token):
        actors = {'owner-a': (1, 10), 'owner-b': (2, 10), 'other-tenant': (1, 11)}
        if token not in actors:
            raise ValueError
        account, tenant = actors[token]
        return Actor(account_id=UUID(int=account), tenant_id=UUID(int=tenant), scopes=(
            'matching:recommendations:write', 'matching:recommendations:read',
            'matching:recommendations:deliver', 'matching:recommendations:correct',
        ))


class Extractor:
    calls = []

    def extract(self, source, key, correlation_id):
        self.calls.append(key)
        return GatewayExtraction(requirements=(Candidate(category='skill', description='Python',
            required=True, evidence=('Python required.',)),), provenance=Provenance(
            model_version='fixture', prompt_version='fixture-v1'))


def profile(account, revision, level, *, contact=False, threshold=70):
    return {'kind': 'profile', 'eventId': uid(account * 1000 + revision),
            'occurredAt': '2026-11-26T09:00:00Z', 'revision': revision, 'contactOnly': contact,
            'profile': {'accountId': uid(account), 'tenantId': uid(10),
                        'snapshotId': uid(account * 100 + revision), 'confirmedFacts': [
                            {'factId': uid(51), 'key': 'Python', 'level': level},
                        ]},
            'criteria': {'criteriaVersionId': uid(account * 100 + 10), 'threshold': threshold}}


def opportunity(account, revision, *, group=71, version=81, status='active', link=False):
    material = [] if link else [{'requirementId': uid(61), 'key': 'Python', 'minimumLevel': 4,
                                'mandatory': True, 'hardEligibility': True,
                                'statement': 'Python required.'}]
    command = {'kind': 'opportunity', 'eventId': uid(10000 + group * 100 + revision + account * 10),
               'occurredAt': '2026-11-26T08:30:00Z', 'revision': revision,
               'job': {'groupId': uid(group), 'title': 'Synthetic Engineer', 'status': status,
                       'opportunity': {'accountId': uid(account), 'tenantId': uid(10),
                           'versionId': uid(version), 'sourceAccess': 'external_to_verify' if link else 'full_text',
                           'requirements': material}}}
    if not link:
        description = 'Revised synthetic position.' if version == 82 else 'Synthetic position.'
        command['source'] = {'jobText': f'Python required. {description}', 'sourceLanguage': 'en'}
    return command


engine = create_engine('sqlite://', poolclass=StaticPool, connect_args={'check_same_thread': False})
extractor = Extractor()
settings = Settings(oidc_issuer='https://identity.example.invalid', oidc_audience='fixture',
                    oidc_jwks_url='https://identity.example.invalid/jwks')
with TestClient(create_app(settings, Identity(), extractor, SqlRecommendationStore(engine),
                           SqlMigrations(engine))) as api:
    def call(path, *, token='owner-a', payload=None, status=200):
        headers = {'Authorization': f'Bearer {token}'}
        response = api.get(path, headers=headers) if payload is None else api.post(path, headers=headers, json=payload)
        assert response.status_code == status, response.text
        return response.json()

    def update(payload, token='owner-a', status=200):
        path = '/v1/internal/recommendation-corrections' if payload['kind'] == 'correction' else '/v1/internal/recommendation-updates'
        return call(path, token=token, payload=payload, status=status)

    def listing(token='owner-a'):
        return call('/v1/recommendations', token=token)['items']

    def outbox(token='owner-a'):
        return call('/v1/internal/recommendation-events', token=token)['items']

    detail = f'/v1/recommendations/{uid(71)}'
    update(profile(1, 1, 5))
    update(profile(2, 1, 1), 'owner-b')
    original = opportunity(1, 1)
    assert update(original)['emitted'] == 1
    assert update(original)['outcome'] == 'duplicate'
    assert update(opportunity(1, 2))['evaluated'] == 0
    assert update(opportunity(2, 1), 'owner-b')['emitted'] == 0
    assert len(extractor.calls) == 1
    assert call(f'{detail}/extraction', token='owner-b')['provenance']['modelVersion'] == 'fixture'
    assert not listing('owner-b')
    assert call(detail, token='owner-b')['reason'] == 'hard_conflict'
    assert call(detail, token='other-tenant', status=404)['code'] == 'SNAPSHOT_NOT_FOUND'
    assert update(opportunity(1, 3), 'owner-b', status=404)['code'] == 'SNAPSHOT_NOT_FOUND'
    first = listing()[0]
    assert first['match']['score'] == 100 and first['match']['findings'][0]['factId'] == uid(51)
    assert first['match']['explanation']['assessedRequirements'] == 1
    assert 'prioritization' in first['match']['limitation']
    assert outbox()[0]['type'] == 'com.careeros.recommendation.created.v1'

    assert update(profile(1, 2, 0, contact=True))['outcome'] == 'irrelevant'
    assert listing()[0]['match']['profileSnapshotId'] == uid(101)
    assert update(profile(1, 3, 4))['emitted'] == 0
    assert listing()[0]['match']['profileSnapshotId'] == uid(103)
    assert update(profile(1, 4, 1))['emitted'] == 0
    assert not listing() and call(detail)['reason'] == 'hard_conflict'
    assert update(profile(1, 5, 5))['emitted'] == 1
    assert len(outbox()) == 2 and len(extractor.calls) == 1

    changed = opportunity(1, 3, version=82)
    assert update(changed)['evaluated'] == 1
    assert listing()[0]['match']['opportunityVersionId'] == uid(82)
    assert len(outbox()) == 2 and len(extractor.calls) == 2
    correction = opportunity(1, 4, version=82)
    correction['kind'] = 'correction'
    correction['job']['opportunity']['requirements'][0]['minimumLevel'] = 5
    assert update(correction)['evaluated'] == 1
    assert update(correction)['outcome'] == 'duplicate'
    history = call(f'{detail}/history')['items']
    assert any(row['match']['opportunityVersionId'] == uid(81) for row in history)
    assert any(row['match']['findings'][0]['minimumLevel'] == 4 for row in history)
    assert call(detail)['match']['findings'][0]['minimumLevel'] == 5
    assert len(extractor.calls) == 2 and len(outbox()) == 2

    update(opportunity(1, 5, version=82, status='ignored'))
    assert not listing() and call(detail)['reason'] == 'ignored'
    update(opportunity(1, 1, group=72, version=83, link=True))
    link = listing()[0]
    assert link['state'] == 'unassessed' and link['match']['sourceAccess'] == 'external_to_verify'
    assert link['match']['score'] is None and link['match']['hardConflicts'] == []
    assert not outbox('owner-b') and len(outbox()) == 2 and len(extractor.calls) == 2

    lower_profile = profile(1, 6, 2)
    update(lower_profile)
    stale = {**profile(1, 5, 5), 'eventId': uid(19001)}
    assert update(stale)['outcome'] == 'stale'
    soft = opportunity(1, 1, group=73, version=84)
    soft['job']['opportunity']['requirements'][0]['hardEligibility'] = False
    assert update(soft)['emitted'] == 0
    soft_detail = f'/v1/recommendations/{uid(73)}'
    assert call(soft_detail)['reason'] == 'below_threshold'
    reduced_threshold = profile(1, 7, 2, threshold=40)
    reduced_threshold['criteria']['criteriaVersionId'] = uid(118)
    assert update(reduced_threshold)['emitted'] == 1
    assert listing()[0]['groupId'] == uid(73) and listing()[0]['match']['score'] == 50
    expired = opportunity(1, 2, group=73, version=84, status='expired')
    expired['job']['opportunity']['requirements'][0]['hardEligibility'] = False
    assert update(expired)['emitted'] == 0
    assert call(soft_detail)['reason'] == 'expired'
    assert all(row['groupId'] != uid(73) for row in listing()) and len(outbox()) == 3

    with_duration = profile(1, 8, 5, threshold=40)
    with_duration['criteria']['criteriaVersionId'] = uid(118)
    with_duration['profile']['confirmedFacts'][0]['experienceMonths'] = 24
    update(with_duration)
    quantified = opportunity(1, 1, group=74, version=85)
    statement = 'Python: at least 5 years of experience.'
    quantified['source']['jobText'] += f' {statement}'
    quantified['job']['opportunity']['requirements'][0].update(
        minimumLevel=1, hardEligibility=False, statement=statement,
    )
    assert update(quantified)['emitted'] == 0
    quantified_detail = f'/v1/recommendations/{uid(74)}'
    blocked = call(quantified_detail)
    assert blocked['reason'] == 'hard_conflict' and blocked['match']['hardConflicts'] == [uid(61)]
    finding = blocked['match']['findings'][0]
    assert finding['statement'] == statement
    assert finding['qualification'] == {
        'unit': 'experience_months', 'required': 60, 'confirmed': 24, 'status': 'not_met',
    }
    without_duration = profile(1, 9, 5, threshold=40)
    without_duration['criteria']['criteriaVersionId'] = uid(118)
    update(without_duration)
    unknown = call(quantified_detail)
    assert unknown['match']['hardConflicts'] == []
    assert unknown['match']['findings'][0]['qualification']['status'] == 'unknown'

print('V1-058 HTTP acceptance passed for recommendation decisions, evidence, ownership and replay.')
