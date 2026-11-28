from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import httpx2
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine

from careeros_resume.adapters.documents import DocumentRenderer
from careeros_resume.adapters.draft_sources import HttpDraftSources
from careeros_resume.adapters.http import create_app
from careeros_resume.adapters.postgresql.migrations.runner import SqlMigrations
from careeros_resume.adapters.postgresql.store import SqlVersions
from careeros_resume.application.drafts import GenerateDraft
from careeros_resume.application.exports import ResumeExports
from careeros_resume.application.recommendations import RecommendationResumes
from careeros_resume.application.versions import Actor, RegistrationConflict, StartResume, Versions


def uid(number):
    return str(UUID(int=number))


pins = {
    'recommendationId': uid(11), 'evaluationId': uid(12), 'groupId': uid(13),
    'opportunityVersionId': uid(14), 'profileSnapshotId': uid(15), 'criteriaVersionId': uid(16),
}
selected = {
    'kind': 'experience', 'itemId': uid(21), 'validationStatus': 'userConfirmed',
    'title': 'Platform Engineer', 'employer': 'Example Studio', 'startDate': '2020-01-01',
    'current': True, 'description': 'Maintained synthetic build systems.',
    'internalScore': 'private-score-marker', 'prompt': 'hidden-prompt-marker',
}
unrelated = {'kind': 'skill', 'itemId': uid(22), 'validationStatus': 'userConfirmed', 'name': 'Unrelated marker'}
corrected = {**selected, 'description': 'Maintained synthetic release systems.'}
state = {'pins': pins, 'live': selected, 'outage': False, 'link': False, 'unsupported': False}


def upstream(request):
    if request.headers['authorization'] == 'Bearer other':
        return httpx2.Response(404)
    path = request.url.path
    current = state['pins']
    if path == f"/v1/recommendations/{current['groupId']}":
        if state['outage']:
            return httpx2.Response(503)
        findings = [{
            'requirementId': uid(31), 'statement': 'Certification required by the source.',
            'factId': None, 'status': 'unknown',
        }]
        if not state['unsupported']:
            findings.append({'requirementId': uid(32), 'statement': 'Build systems experience.',
                             'factId': uid(21), 'status': 'satisfied'})
        return httpx2.Response(200, json={
            **current, 'state': 'active', 'reason': 'qualified', 'match': {
                'profileSnapshotId': current['profileSnapshotId'],
                'opportunityVersionId': current['opportunityVersionId'],
                'sourceAccess': 'external_to_verify' if state['link'] else 'full_text',
                'findings': findings,
            },
        })
    if path.startswith('/v1/profile/snapshots/'):
        snapshot = path.rsplit('/', 1)[1]
        fact = selected if snapshot == uid(15) else corrected
        return httpx2.Response(200, json={'snapshotId': snapshot, 'items': [fact, unrelated]})
    if path == '/v1/profile/items':
        if len(request.url.params.get_list('cursor')) == 0:
            return httpx2.Response(200, json={'items': [unrelated], 'page': {'nextCursor': 'next example'}})
        assert request.url.params['cursor'] == 'next example'
        return httpx2.Response(200, json={'items': [state['live']], 'page': {}})
    if path == f"/v1/jobs/{current['opportunityVersionId']}":
        return httpx2.Response(200, json={
            'opportunityId': current['opportunityVersionId'], 'sourceAccess': 'full_text',
        })
    return httpx2.Response(404)


class Verifier:
    def verify(self, token):
        if token not in {'owner', 'other', 'review-only'}:
            raise ValueError('Fixture identity unavailable')
        scopes = ('resume:drafts:generate', 'resume:versions:read', 'profile:read', 'jobs:read',
                  'resume:versions:write', 'matching:recommendations:read')
        if token != 'review-only':
            scopes += ('resume:versions:approve',)
        return Actor(account_id=UUID(int=2 if token == 'other' else 1), tenant_id=UUID(int=10), scopes=scopes)


class Storage:
    def __init__(self):
        self.data = {}

    def write(self, scope, artifact, content, fingerprint):
        record = content, fingerprint
        if self.data.setdefault((scope, artifact.object_key), record) != record:
            raise RegistrationConflict

    def read(self, scope, artifact):
        return self.data[scope, artifact.object_key][0]


with TemporaryDirectory() as directory:
    engine = create_engine(f"sqlite:///{(Path(directory) / 'recommendation.sqlite').as_posix()}")
    with httpx2.Client(transport=httpx2.MockTransport(upstream)) as transport:
        sources = HttpDraftSources(transport, 'https://profile.example.invalid',
                                   'https://jobs.example.invalid', 'https://matching.example.invalid')
        drafts = GenerateDraft(sources)
        versions = Versions(SqlVersions(engine))
        exports = ResumeExports(drafts, versions, DocumentRenderer(), Storage())
        app = create_app(versions, StartResume(SqlMigrations(engine)), Verifier(), engine.dispose,
                         drafts=drafts, exports=exports,
                         recommended=RecommendationResumes(sources, drafts, exports, versions))
        with TestClient(app) as client:
            owner = {'Authorization': 'Bearer owner'}
            other = {'Authorization': 'Bearer other'}
            review_only = {'Authorization': 'Bearer review-only'}

            def create(payload=pins, key=51, headers=owner):
                return client.post('/v1/recommendation-resumes',
                                   json=payload, headers={**headers, 'Idempotency-Key': uid(key)})

            state['unsupported'] = True
            missing = create()
            assert missing.status_code == 422 and missing.json()['code'] == 'missing_facts'
            assert missing.json()['missingRequirements'][0]['requirementId'] == uid(31)
            state['unsupported'] = False
            state['link'] = True
            assert create().json()['code'] == 'full_text_required'
            state['link'] = False
            state['outage'] = True
            assert create().status_code == 503
            state['outage'] = False
            assert create({**pins, 'criteriaVersionId': uid(99)}).json()['code'] == 'stale_snapshot'
            assert create(headers=other).status_code == 404
            first = create()
            assert first.status_code == 201, first.text
            version = first.json()
            assert version['recommendation']['pins'] == pins and version['version'] == 1
            proof = version['recommendation']['facts']
            assert [fact['sourceFactId'] for fact in proof] == [uid(21)]
            assert proof[0]['requirementIds'] == [uid(32)]
            assert version['recommendation']['missingRequirements'][0]['requirementId'] == uid(31)
            assert create().status_code == 200 and create().json() == version

            root = f"/v1/resumes/{pins['recommendationId']}/versions/1"
            review = client.get(f'{root}/review', headers=owner)
            assert not review.json()['eligibleForPackage'] and review.json()['approval'] is None
            assert client.get(f'{root}/review', headers=other).status_code == 404
            pdf = client.get(f'{root}/artifacts/pdf', headers=owner)
            text = ' '.join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
            assert 'Maintained synthetic build systems.' in text
            for forbidden in ('Unrelated marker', 'private-score-marker', 'hidden-prompt-marker', 'Certification required'):
                assert forbidden not in text
            approve = {'approved': True, 'pdfSha256': version['artifacts'][0]['sha256']}
            endpoint = f'{root}/approval'
            assert client.post(endpoint, headers=review_only, json=approve).status_code == 403
            assert client.post(endpoint, headers=owner, json={**approve, 'approved': False}).status_code == 422
            assert client.post(endpoint, headers=owner, json={**approve, 'pdfSha256': 'a' * 64}).status_code == 422
            receipt = client.post(endpoint, headers=owner, json=approve)
            assert receipt.status_code == 200 and receipt.json()['eligibleForPackage']
            assert client.post(endpoint, headers=owner, json=approve).json() == receipt.json()

            state['live'] = corrected
            stale = client.get(f'{root}/review', headers=owner).json()
            assert not stale['current'] and not stale['eligibleForPackage']
            assert stale['approval'] == receipt.json()['approval']
            assert client.post(endpoint, headers=owner, json=approve).json()['code'] == 'stale_snapshot'
            assert client.get(f'{root}/artifacts/pdf', headers=owner).content == pdf.content
            assert create().json() == version
            assert create(key=52).json()['code'] == 'stale_snapshot'

            new_pins = {**pins, 'profileSnapshotId': uid(36), 'evaluationId': uid(37)}
            state['pins'] = new_pins
            assert create(new_pins).status_code == 409
            second = create(new_pins, key=52)
            assert second.status_code == 201 and second.json()['version'] == 2
            assert second.json()['recommendation']['pins'] == new_pins
            third = create(new_pins, key=53)
            assert third.status_code == 201 and third.json()['version'] == 3
            assert create(new_pins, key=53).json() == third.json()
            assert client.get(f'{root}/review', headers=owner).json() == stale

print('V1-059 HTTP acceptance passed for pinned selection, preview, approval and stale facts.')
