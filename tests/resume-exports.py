from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID
from zipfile import ZipFile

import httpx2
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import create_engine

from careeros_resume.adapters.documents import DocumentRenderer
from careeros_resume.adapters.draft_sources import HttpDraftSources
from careeros_resume.adapters.http import create_app
from careeros_resume.adapters.postgresql.migrations.runner import SqlMigrations
from careeros_resume.adapters.postgresql.store import SqlVersions
from careeros_resume.application.drafts import GenerateDraft, SourceUnavailable
from careeros_resume.application.exports import ResumeExports
from careeros_resume.application.versions import Actor, NotFound, RegistrationConflict, StartResume, Versions


def uid(number):
    return str(UUID(int=number))


class FixtureVerifier:
    def verify(self, token):
        identities = {'owner': (1, 10), 'other': (2, 10), 'tenant': (1, 11)}
        if token not in identities:
            raise ValueError('Invalid fixture identity')
        account, tenant = identities[token]
        return Actor(account_id=UUID(int=account), tenant_id=UUID(int=tenant), scopes=(
            'profile:read', 'resume:drafts:generate', 'resume:versions:read', 'resume:versions:write',
        ))


class MemoryArtifacts:
    def __init__(self):
        self.objects = {}
        self.reads = 0
        self.interrupt_docx = False

    def write(self, scope, artifact, data, fingerprint):
        if self.interrupt_docx and artifact.format == 'docx':
            raise SourceUnavailable
        key = scope, artifact.object_key
        payload = data, fingerprint
        if self.objects.setdefault(key, payload) != payload:
            raise RegistrationConflict

    def read(self, scope, artifact):
        self.reads += 1
        try:
            return self.objects[scope, artifact.object_key][0]
        except KeyError:
            raise NotFound from None


experience = {
    'kind': 'experience', 'itemId': uid(11), 'validationStatus': 'userConfirmed',
    'title': 'Ingénieure logiciel', 'employer': 'Atelier Exemple', 'startDate': '2020-01-01',
    'current': True, 'description': 'Maintained <build> & release systems.',
    'internalScore': 'private-score-marker', 'prompt': 'hidden-prompt-marker',
    'internalNotes': 'internal-comment-marker', 'contact': 'unrelated-personal-marker',
}
skill = {
    'kind': 'skill', 'itemId': uid(12), 'validationStatus': 'userConfirmed',
    'name': 'Python', 'level': 'advanced', 'levelSource': 'selfDeclared',
}
suggestion = {
    **skill, 'itemId': uid(13), 'validationStatus': 'unconfirmed', 'name': 'unconfirmed-marker',
}
markers = (
    'private-score-marker', 'hidden-prompt-marker', 'internal-comment-marker',
    'unrelated-personal-marker', 'unconfirmed-marker',
)


def profile(request):
    assert request.headers['authorization'] == 'Bearer owner'
    assert request.url.path == f'/v1/profile/snapshots/{uid(31)}'
    return httpx2.Response(200, json={
        'snapshotId': uid(31), 'items': [experience, suggestion, skill],
    })


def normalized(text):
    return ' '.join(text.split())


with TemporaryDirectory() as directory:
    engine = create_engine(f"sqlite:///{(Path(directory) / 'exports.sqlite').as_posix()}")
    storage = MemoryArtifacts()
    with httpx2.Client(transport=httpx2.MockTransport(profile)) as transport:
        drafts = GenerateDraft(HttpDraftSources(transport, 'https://profiles.example.invalid', None))
        versions = Versions(SqlVersions(engine))
        exports = ResumeExports(drafts, versions, DocumentRenderer(), storage)
        app = create_app(
            versions, StartResume(SqlMigrations(engine)), FixtureVerifier(), engine.dispose,
            drafts=drafts, exports=exports,
        )
        with TestClient(app) as client:
            root = f'/v1/resumes/{uid(21)}'
            request = {'profileSnapshotId': uid(31)}
            headers = {'Authorization': 'Bearer owner', 'Idempotency-Key': uid(51)}
            rendered = client.post(f'{root}/exports', headers=headers, json=request)
            assert rendered.status_code == 201, rendered.text
            version = rendered.json()
            assert version['version'] == 1 and version['profileSnapshotId'] == uid(31)
            assert rendered.headers['location'] == f'{root}/versions/1'
            assert [item['format'] for item in version['artifacts']] == ['pdf', 'docx']
            replay = client.post(f'{root}/exports', headers=headers, json=request)
            assert replay.status_code == 200 and replay.json() == version
            changed = client.post(f'{root}/exports', headers=headers, json={**request, 'factIds': [uid(12)]})
            assert changed.status_code == 409
            assert len(storage.objects) == 2
            assert client.get(f'{root}/versions', headers=headers).json()['items'] == [version]

            extracted = {}
            for artifact in version['artifacts']:
                name = artifact['format']
                path = f'{root}/versions/1/artifacts/{name}'
                file = client.get(path, headers=headers)
                assert file.status_code == 200
                assert file.headers['content-disposition'] == f'attachment; filename="resume.{name}"'
                assert file.headers['cache-control'] == 'no-store'
                assert len(file.content) == artifact['byteSize']
                assert sha256(file.content).hexdigest() == artifact['sha256']
                if name == 'pdf':
                    assert file.headers['content-type'] == 'application/pdf'
                    pdf = PdfReader(BytesIO(file.content))
                    extracted[name] = '\n'.join(page.extract_text() for page in pdf.pages)
                    metadata = str(pdf.metadata)
                else:
                    assert file.headers['content-type'].endswith('wordprocessingml.document')
                    doc = Document(BytesIO(file.content))
                    assert any(p.style.name == 'Heading 1' for p in doc.paragraphs)
                    extracted[name] = '\n'.join(p.text for p in doc.paragraphs)
                    with ZipFile(BytesIO(file.content)) as archive:
                        assert 'word/comments.xml' not in archive.namelist()
                        metadata = archive.read('docProps/core.xml').decode()
                assert all(marker not in extracted[name] + metadata for marker in markers)

            assert normalized(extracted['pdf']) == normalized(extracted['docx'])
            assert 'Ingénieure logiciel' in extracted['pdf']
            assert 'Maintained <build> & release systems.' in extracted['pdf']
            assert normalized(extracted['pdf']).index('Experience') < normalized(extracted['pdf']).index('Skills')
            path = f'{root}/versions/1/artifacts/pdf'
            reads = storage.reads
            for other in ('other', 'tenant'):
                assert client.get(path, headers={'Authorization': f'Bearer {other}'}).status_code == 404
            assert client.get(path).status_code == 401
            assert storage.reads == reads
            key = next(key for key in storage.objects if str(key[1]) == version['artifacts'][0]['objectKey'])
            data, fingerprint = storage.objects[key]
            storage.objects[key] = data[:-1] + b'X', fingerprint
            assert client.get(path, headers=headers).status_code == 502

            new_headers = {**headers, 'Idempotency-Key': uid(52)}
            storage.interrupt_docx = True
            interrupted = client.post(f'{root}/exports', headers=new_headers, json=request)
            assert interrupted.status_code == 503
            assert client.get(f'{root}/versions', headers=headers).json()['items'] == [version]
            assert len(storage.objects) == 3
            storage.interrupt_docx = False
            retried = client.post(f'{root}/exports', headers=new_headers, json=request)
            assert retried.status_code == 201 and retried.json()['version'] == 2
            assert len(retried.json()['artifacts']) == 2 and len(storage.objects) == 4

print('V1-029 HTTP acceptance passed for extractable, immutable and owned resume exports.')
