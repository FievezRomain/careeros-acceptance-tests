from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

import httpx2
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from careeros_resume.adapters.draft_sources import HttpDraftSources
from careeros_resume.adapters.http import create_app
from careeros_resume.adapters.postgresql.migrations.runner import SqlMigrations
from careeros_resume.adapters.postgresql.store import SqlVersions
from careeros_resume.application.drafts import GenerateDraft
from careeros_resume.application.versions import Actor, StartResume, Versions


def uid(number):
    return str(UUID(int=number))


snapshot_id, job_id, link_id = uid(31), uid(41), uid(42)
experience = {
    'kind': 'experience', 'itemId': uid(11), 'validationStatus': 'userConfirmed',
    'title': 'Platform Engineer', 'employer': 'Example Studio', 'startDate': '2022-01-01',
    'endDate': None, 'current': True, 'description': 'Maintained the synthetic build system.',
    'provenance': {'origin': 'directEntry'}, 'internalNotes': 'Private annotation',
    'sourceFactId': uid(99),
}
skill = {
    'kind': 'skill', 'itemId': uid(12), 'validationStatus': 'userConfirmed',
    'name': 'Python', 'level': 'advanced', 'levelSource': 'selfDeclared',
}
suggestion = {
    **experience, 'itemId': uid(13), 'validationStatus': 'unconfirmed',
    'employer': 'Invented employer', 'description': 'Invented 99% improvement',
}
calls = []


def upstream(request):
    token = request.headers['authorization']
    path = request.url.path
    UUID(request.headers['x-correlation-id'])
    calls.append((request.url.host, path))
    if token in {'Bearer other', 'Bearer other-tenant'}:
        return httpx2.Response(404, json={'detail': 'Private source error'})
    assert token == 'Bearer owner'
    if request.url.host == 'profiles.example.invalid' and path == f'/v1/profile/snapshots/{snapshot_id}':
        return httpx2.Response(200, json={
            'snapshotId': snapshot_id, 'createdAt': '2026-11-20T09:00:00Z',
            'items': [experience, suggestion, skill],
        })
    if request.url.host == 'jobs.example.invalid' and path in {f'/v1/jobs/{job_id}', f'/v1/jobs/{link_id}'}:
        return httpx2.Response(200, json={
            'opportunityId': path.rsplit('/', 1)[1],
            'sourceAccess': 'full_text' if path.endswith(job_id) else 'external_to_verify',
            'description': 'Invented claims from a job description',
        })
    return httpx2.Response(404)


class FixtureVerifier:
    def verify(self, token):
        actors = {
            'owner': (1, 10, ('resume:drafts:generate', 'profile:read', 'jobs:read')),
            'other': (2, 10, ('resume:drafts:generate', 'profile:read', 'jobs:read')),
            'other-tenant': (1, 11, ('resume:drafts:generate', 'profile:read')),
            'read-only': (1, 10, ('profile:read',)),
        }
        if token not in actors:
            raise ValueError('Invalid fixture identity')
        account, tenant, scopes = actors[token]
        return Actor(account_id=UUID(int=account), tenant_id=UUID(int=tenant), scopes=scopes)


with TemporaryDirectory() as directory:
    engine = create_engine(f"sqlite:///{(Path(directory) / 'drafts.sqlite').as_posix()}")
    with httpx2.Client(transport=httpx2.MockTransport(upstream)) as transport:
        source = HttpDraftSources(transport, 'https://profiles.example.invalid', 'https://jobs.example.invalid')
        app = create_app(
            Versions(SqlVersions(engine)), StartResume(SqlMigrations(engine)), FixtureVerifier(),
            engine.dispose, drafts=GenerateDraft(source),
        )
        with TestClient(app) as client:
            def draft(token='owner', **fields):
                return client.post('/v1/resume-drafts', headers={'Authorization': f'Bearer {token}'},
                                   json={'profileSnapshotId': snapshot_id, **fields})

            result = draft(opportunityVersionId=job_id)
            assert result.status_code == 200, result.text
            body = result.json()
            assert body['profileSnapshotId'] == snapshot_id and body['opportunityVersionId'] == job_id
            assert [item['sourceFactId'] for item in body['entries']] == [uid(11), uid(12)]
            fact = body['entries'][0]
            for key in ('title', 'employer', 'startDate', 'endDate', 'current', 'description'):
                assert fact[key] == experience[key]
            assert body['entries'][1]['levelSource'] == 'selfDeclared'
            assert not any(text in result.text for text in ('Invented', 'Private annotation', 'validationStatus'))
            assert draft(opportunityVersionId=job_id).json() == body

            selected = draft(factIds=[uid(12)])
            assert selected.status_code == 200
            assert [item['sourceFactId'] for item in selected.json()['entries']] == [uid(12)]
            assert selected.json()['opportunityVersionId'] is None
            assert draft(factIds=[uid(13)]).status_code == 422
            assert draft(factIds=[uid(11), uid(99)]).status_code == 422
            assert draft(factIds=[uid(11), uid(11)]).status_code == 422
            assert draft(employer='Caller-supplied employer').status_code == 422
            assert draft(opportunityVersionId=link_id).status_code == 422
            denied = draft('other')
            assert denied.status_code == 404 and 'Private source error' not in denied.text
            assert draft('other-tenant').status_code == 404
            assert draft(opportunityVersionId=uid(99)).status_code == 404
            before = len(calls)
            assert draft('read-only').status_code == 403
            assert draft('unknown').status_code == 401
            assert len(calls) == before

print('V1-028 HTTP acceptance passed for confirmed facts and owned draft provenance.')
