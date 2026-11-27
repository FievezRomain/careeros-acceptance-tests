"""V1-024 HTTP acceptance with the real matching-to-gateway protocol adapter."""

import json
from uuid import UUID

import httpx2
from fastapi.testclient import TestClient

from careeros_matching.adapters.gateway import HttpRequirementGateway
from careeros_matching.adapters.http import Settings, create_app
from careeros_matching.application.scoring import Actor


def uid(number):
    return str(UUID(int=number))


class FixtureVerifier:
    def verify(self, token):
        assert token == 'fixture-actor'
        return Actor(account_id=UUID(int=1), tenant_id=UUID(int=2), scopes=('matching:extract',))


phrase = 'Python is required for this position.'
calls = []
suggestions = [
    {'category': 'skill', 'description': 'Python', 'required': True, 'evidence': [phrase]},
    {'category': 'skill', 'description': 'Go', 'required': True, 'evidence': [phrase]},
    {'category': 'skill', 'description': 'Python', 'required': True, 'evidence': ['Python is optional.']},
]


def gateway(request):
    calls.append(request)
    assert request.url.path == '/v1/capabilities/extract-job-requirements/invocations'
    assert request.headers['Authorization'] == 'Bearer synthetic-gateway'
    assert request.headers['X-Correlation-ID'] == uid(9)
    assert json.loads(request.content) == {
        'capabilityVersion': '1.0', 'inputSchemaVersion': '1.0',
        'input': {'jobText': phrase, 'sourceLanguage': 'en'},
    }
    return httpx2.Response(200, json={
        'capabilityId': 'extract-job-requirements', 'capabilityVersion': '1.0',
        'outputSchemaVersion': '1.0', 'output': {'requirements': suggestions},
        'provenance': {'modelVersion': 'synthetic-v1', 'promptVersion': 'prompt-v1', 'inputUnits': 8},
    })


settings = Settings(oidc_issuer='https://identity.example.invalid', oidc_audience='fixture',
                    oidc_jwks_url='https://identity.example.invalid/jwks')
command = {'accountId': uid(1), 'tenantId': uid(2), 'opportunityVersionId': uid(3),
           'sourceAccess': 'full_text', 'jobText': phrase, 'sourceLanguage': 'en'}
with httpx2.Client(transport=httpx2.MockTransport(gateway)) as client:
    extractor = HttpRequirementGateway(client, 'https://gateway.example.invalid/', 'synthetic-gateway')
    with TestClient(create_app(settings, FixtureVerifier(), extractor)) as app:
        def post(payload):
            return app.post('/v1/internal/requirements/extract', json=payload, headers={
                'Authorization': 'Bearer fixture-actor', 'X-Correlation-ID': uid(9),
            })

        response = post(command)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['status'] == 'partial' and result['rejectedCount'] == 2
        assert result['opportunityVersionId'] == uid(3)
        assert result['extractorVersion'] == 'requirements-v1'
        assert result['provenance']['modelVersion'] == 'synthetic-v1'
        assert result['provenance']['promptVersion'] == 'prompt-v1'
        assert len(result['suggestions']) == 1
        suggestion = result['suggestions'][0]
        assert suggestion['description'] == 'Python' and suggestion['suggestedMandatory'] is True
        assert suggestion['evidence'] == [phrase]
        assert post(command).json() == result
        assert calls[0].headers['Idempotency-Key'] == calls[1].headers['Idempotency-Key']

        suggestions.pop(0)
        inconclusive = post(command).json()
        assert inconclusive['status'] == 'inconclusive' and inconclusive['suggestions'] == []
        assert len(calls) == 3

        link = {key: value for key, value in command.items() if key not in {'jobText', 'sourceLanguage'}}
        link['sourceAccess'] = 'external_to_verify'
        unassessed = post(link).json()
        assert unassessed['status'] == 'external_to_verify' and unassessed['provenance'] is None
        assert post({**command, 'accountId': uid(99)}).status_code == 404
        assert len(calls) == 3

print('V1-024 HTTP acceptance passed for evidence, uncertainty and ownership.')
