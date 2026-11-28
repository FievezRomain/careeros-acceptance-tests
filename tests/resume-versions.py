from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from careeros_resume.adapters.http import create_app
from careeros_resume.adapters.postgresql.migrations.runner import SqlMigrations
from careeros_resume.adapters.postgresql.store import SqlVersions
from careeros_resume.application.versions import Actor, StartResume, Versions


def uid(number):
    return str(UUID(int=number))


class FixtureVerifier:
    def verify(self, token):
        account, tenant, scopes = {
            'owner': (1, 10, ['resume:versions:read', 'resume:versions:write']),
            'other': (2, 10, ['resume:versions:read', 'resume:versions:write']),
            'tenant': (1, 11, ['resume:versions:read']),
            'read-only': (1, 10, ['resume:versions:read']),
        }[token]
        return Actor(account_id=UUID(int=account), tenant_id=UUID(int=tenant), scopes=scopes)


def headers(token='owner', key=51):
    return {'Authorization': f'Bearer {token}', 'Idempotency-Key': uid(key)}


path = f'/v1/resumes/{uid(21)}/versions'
pdf = {'format': 'pdf', 'objectKey': uid(31), 'sha256': 'a' * 64, 'byteSize': 120}
docx = {'format': 'docx', 'objectKey': uid(32), 'sha256': 'b' * 64, 'byteSize': 280}
original = {'profileSnapshotId': uid(41), 'opportunityVersionId': uid(42), 'artifacts': [pdf]}
edited = {'profileSnapshotId': uid(43), 'opportunityVersionId': uid(44), 'artifacts': [docx]}

with TemporaryDirectory() as directory:
    url = f"sqlite:///{(Path(directory) / 'resume.sqlite').as_posix()}"
    engine = create_engine(url)
    try:
        def app():
            return create_app(Versions(SqlVersions(engine)), StartResume(SqlMigrations(engine)), FixtureVerifier())

        with TestClient(app()) as client:
            first = client.post(path, headers=headers(), json=original)
            assert first.status_code == 201, first.text
            assert first.json()['version'] == 1
            assert first.json()['artifacts'] == [pdf]
            assert first.headers['location'] == f'{path}/1'
            replay = client.post(path, headers=headers(), json=original)
            assert replay.status_code == 200 and replay.json() == first.json()
            assert client.post(path, headers=headers(), json=edited).status_code == 409
            invalid = {**edited, 'artifacts': [{**docx, 'sha256': 'invalid'}]}
            assert client.post(path, headers=headers(key=52), json=invalid).status_code == 422
            assert client.post(path, headers=headers('read-only', 52), json=edited).status_code == 403
            second = client.post(path, headers=headers(key=52), json=edited)
            assert second.status_code == 201 and second.json()['version'] == 2
            assert second.json()['artifacts'] == [docx]

        with TestClient(app()) as client:
            history = client.get(path, headers=headers(), params={'limit': 1}).json()
            assert history == {'items': [first.json()], 'nextAfter': 1}
            tail = client.get(path, headers=headers(), params={'after': 1}).json()
            assert tail == {'items': [second.json()], 'nextAfter': None}
            earlier = client.get(f'{path}/1', headers=headers()).json()
            assert earlier == first.json()
            assert earlier['profileSnapshotId'] == original['profileSnapshotId']
            assert earlier['opportunityVersionId'] == original['opportunityVersionId']
            for actor in ('other', 'tenant'):
                assert client.get(path, headers=headers(actor)).status_code == 404
                assert client.get(f'{path}/1', headers=headers(actor)).status_code == 404
            assert client.get(f'{path}/1').status_code == 401
    finally:
        engine.dispose()

print('V1-027 HTTP acceptance passed for immutable resume versions, retries and ownership.')
