"""Exercise the ATS public API and its delegation to the final artifact route."""

import sys
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from uuid import UUID
from zipfile import ZipFile

import httpx2
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas

from careeros_ats.adapters.documents import DocumentText
from careeros_ats.adapters.http import create_app
from careeros_ats.adapters.matching import HttpRequirementEvidence
from careeros_ats.adapters.oidc import OidcVerifier
from careeros_ats.adapters.resume import HttpResumeArtifacts
from careeros_ats.application.extraction import ExtractText
from careeros_ats.application.relevance import AssessRelevance

RESUME = UUID(int=301)
OWNER = str(UUID(int=302))
TENANT = str(UUID(int=303))
CORRELATION = str(UUID(int=304))
GROUP = UUID(int=310)
EXTERNAL = UUID(int=311)
OFFER = UUID(int=312)
UNAVAILABLE = UUID(int=313)
OTHER_OFFER = UUID(int=314)
NO_SUGGESTIONS = UUID(int=315)
MALFORMED = UUID(int=316)
ISSUER = "https://identity.example.invalid"
AUDIENCE = "careeros-acceptance"
SCOPES = "ats:extractions:read resume:versions:read"
RELEVANCE_SCOPES = SCOPES + " matching:recommendations:read"
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def pdf(text):
    stream = BytesIO()
    canvas = Canvas(stream)
    for index, line in enumerate(text.splitlines()):
        canvas.drawString(72, 720 - 14 * index, line)
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


def docx():
    stream = BytesIO()
    with ZipFile(stream, "w") as package:
        package.writestr("[Content_Types].xml", """
            <Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
              <Override PartName="/word/document.xml"
                ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
            </Types>
        """)
        package.writestr("word/document.xml", """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>Final DOCX section</w:t></w:r></w:p>
                <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Visible table evidence</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
              </w:body>
            </w:document>
        """)
    return stream.getvalue()


key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
signing_key = jwt.PyJWK.from_dict(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True))


class Keys:
    def get_signing_key_from_jwt(self, token):
        return signing_key


def headers(account=OWNER, tenant=TENANT, scopes=SCOPES):
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": account, "tenant_id": tenant, "scope": scopes, "iss": ISSUER,
         "aud": AUDIENCE, "iat": now, "exp": now + timedelta(minutes=5)},
        key, algorithm="RS256",
    )
    return {"Authorization": f"Bearer {token}", "X-Correlation-ID": CORRELATION}


def extraction(number, kind, report="extraction"):
    return f"/v1/resumes/{RESUME}/versions/{number}/artifacts/{kind}/{report}"


artifacts = {
    (1, "pdf"): (PDF, pdf("Final PDF version one")),
    (2, "pdf"): (PDF, pdf("Final PDF version two")),
    (2, "docx"): (DOCX, docx()),
    (3, "pdf"): (PDF, pdf("")),
    (3, "docx"): (DOCX, b"unreadable synthetic file"),
    (4, "pdf"): (PDF, pdf("Experience\nSynthetic developer\n2022 to 2024\nSkills\nPython")),
    (5, "pdf"): (PDF, pdf("Experience\nSynthetic developer\nSkills\nPython")),
    (6, "pdf"): (PDF, pdf("Skills\nPython")),
    (7, "pdf"): (PDF, pdf("Skills\nPYTHON and C++")),
}
reads = []


def upstream(request):
    claims = jwt.decode(
        request.headers["Authorization"].removeprefix("Bearer "),
        key.public_key(), algorithms=["RS256"], issuer=ISSUER, audience=AUDIENCE,
    )
    assert request.headers["X-Correlation-ID"] == CORRELATION
    if request.url.host == "matching.example.invalid":
        return requirements(request, claims)
    _, api, noun, resume, versions, number, resource, kind = request.url.path.split("/")
    assert (api, noun, resume, versions, resource) == ("v1", "resumes", str(RESUME), "versions", "artifacts")
    assert request.method == "GET"
    reads.append((int(number), kind))
    if (claims["sub"], claims["tenant_id"]) != (OWNER, TENANT):
        return httpx2.Response(404)
    if number == "10":
        return httpx2.Response(503)
    artifact = artifacts.get((int(number), kind))
    if artifact is None:
        return httpx2.Response(404)
    content_type, content = artifact
    return httpx2.Response(200, headers={"Content-Type": content_type}, content=content)


def requirements(request, claims):
    _, api, resource, group, operation = request.url.path.split("/")
    assert (request.method, api, resource, operation) == ("GET", "v1", "recommendations", "extraction")
    if (claims["sub"], claims["tenant_id"]) != (OWNER, TENANT) or "matching:recommendations:read" not in claims["scope"].split():
        return httpx2.Response(404)
    if UUID(group) == UNAVAILABLE:
        return httpx2.Response(503)
    if UUID(group) == MALFORMED:
        return httpx2.Response(200, json={"unexpected": True})
    if UUID(group) not in {GROUP, EXTERNAL, NO_SUGGESTIONS}:
        return httpx2.Response(404)
    status = {EXTERNAL: "external_to_verify", NO_SUGGESTIONS: "inconclusive"}.get(UUID(group), "extracted")
    suggestions = [
        {"requirementId": str(UUID(int=index)), "description": term, "category": "skill",
         "evidence": [quote], "suggestedMandatory": True}
        for index, term, quote in (
            (321, "Python", "Experience using Python."),
            (322, "Kubernetes", "Knowledge of Kubernetes preferred."),
            (323, "C", "Experience using C."),
            (324, "Docker", "Experience using PostgreSQL."),
        )
    ] if status == "extracted" else []
    return httpx2.Response(200, json={
        "opportunityVersionId": str(OFFER), "extractorVersion": "requirements-v1",
        "status": status, "suggestions": suggestions,
    })


def check(client):
    for number, kind, expected in (
        (1, "pdf", "Final PDF version one"),
        (2, "pdf", "Final PDF version two"),
        (2, "docx", "Final DOCX section\nVisible table evidence"),
    ):
        result = client.get(extraction(number, kind), headers=headers())
        assert result.status_code == 200, result.text
        assert result.headers["Cache-Control"] == "no-store"
        assert result.json() == {
            "resumeId": str(RESUME), "version": number, "format": kind,
            "artifactSha256": sha256(artifacts[number, kind][1]).hexdigest(),
            "extractorVersion": "text-v1", "status": "extracted", "text": expected,
        }, result.text
    assert reads == [(1, "pdf"), (2, "pdf"), (2, "docx")]

    for kind, reason in (("pdf", "no_text"), ("docx", "unreadable")):
        response = client.get(extraction(3, kind), headers=headers())
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "inconclusive" and result["reason"] == reason
        assert result["artifactSha256"] == sha256(artifacts[3, kind][1]).hexdigest()
        assert "text" not in result and "score" not in result

    calls = len(reads)
    assert client.get(extraction(1, "pdf")).status_code == 401
    assert client.get(extraction(1, "pdf"), headers=headers(scopes="resume:versions:read")).status_code == 403
    assert client.get(extraction(1, "pdf"), headers=headers(scopes="ats:extractions:read")).status_code == 403
    assert client.get(extraction(0, "pdf"), headers=headers()).status_code == 422
    assert client.get(extraction(1, "rtf"), headers=headers()).status_code == 422
    assert len(reads) == calls
    for identity in (headers(account=str(UUID(int=305))), headers(tenant=str(UUID(int=306)))):
        denied = client.get(extraction(2, "pdf"), headers=identity)
        assert denied.status_code == 404 and "Final PDF" not in denied.text
    assert client.get(extraction(9, "pdf"), headers=headers()).status_code == 404
    assert client.get(extraction(10, "pdf"), headers=headers()).status_code == 503


def check_structure(client):
    def report(number, kind="pdf"):
        response = client.get(extraction(number, kind, "structure"), headers=headers())
        assert response.status_code == 200, response.text
        assert response.headers["Cache-Control"] == "no-store"
        result = response.json()
        assert result["resumeId"] == str(RESUME) and result["version"] == number
        assert result["format"] == kind and result["rubricVersion"] == "structure-v1"
        assert result["artifactSha256"] == sha256(artifacts[number, kind][1]).hexdigest()
        assert "text" not in result
        return result

    complete = report(4)
    assert complete["status"] == "evaluated" and complete["technicalScore"] == 100
    assert complete["applicablePoints"] == complete["earnedPoints"] == 100
    assert all(check["status"] == "passed" for check in complete["checks"])
    assert report(4) == complete

    updated = report(5)
    assert updated["artifactSha256"] != complete["artifactSha256"]
    assert updated["technicalScore"] == updated["earnedPoints"] == 75
    assert updated["applicablePoints"] == 100
    dates = next(check for check in updated["checks"] if check["ruleId"] == "experience_dates")
    assert dates["status"] == "needs_attention" and dates["line"] == 1
    assert "dates" in dates["correction"].lower()
    assert report(4) == complete

    skills = report(6)
    assert skills["technicalScore"] == 100 and skills["applicablePoints"] == 75
    dates = next(check for check in skills["checks"] if check["ruleId"] == "experience_dates")
    assert dates["status"] == "not_applicable"
    docx_report = report(2, "docx")
    assert docx_report["technicalScore"] == 53 and docx_report["applicablePoints"] == 75

    blank = report(3)
    assert blank["status"] == "inconclusive" and blank["reason"] == "no_text"
    assert "technicalScore" not in blank and "checks" not in blank
    route = extraction(4, "pdf", "structure")
    assert client.get(route).status_code == 401
    assert client.get(route, headers=headers(scopes="resume:versions:read")).status_code == 403
    assert client.get(route, headers=headers(tenant=str(UUID(int=306)))).status_code == 404
    assert client.get(extraction(0, "pdf", "structure"), headers=headers()).status_code == 422


def check_relevance(client):
    def response(version=7, kind="pdf", group=GROUP, offer=OFFER, auth=None):
        return client.get(
            extraction(version, kind, "relevance"),
            params={"opportunityGroupId": str(group), "opportunityVersionId": str(offer)},
            headers=headers(scopes=RELEVANCE_SCOPES) if auth is None else auth,
        )

    evaluated = response()
    assert evaluated.status_code == 200, evaluated.text
    assert evaluated.headers["Cache-Control"] == "no-store"
    result = evaluated.json()
    assert result["status"] == "evaluated" and result["relevanceVersion"] == "mentions-v1"
    assert result["opportunityGroupId"] == str(GROUP) and result["opportunityVersionId"] == str(OFFER)
    assert result["artifactSha256"] == sha256(artifacts[7, "pdf"][1]).hexdigest()
    assert result["requirementsStatus"] == "partial"
    assert len(result["requirementsSha256"]) == 64 and result["requirementExtractorVersion"] == "requirements-v1"
    assert "employer" in result["limitation"].lower()
    assert response().json() == result
    findings = {finding["requirement"]["description"]: finding for finding in result["findings"]}
    assert set(findings) == {"Python", "Kubernetes", "C"}
    assert findings["Python"]["status"] == "mentioned"
    assert findings["Python"]["requirement"]["evidence"] == ["Experience using Python."]
    assert findings["Python"]["resumeEvidence"] == {"line": 2, "matchedText": "PYTHON", "excerpt": "PYTHON and C++"}
    assert findings["Kubernetes"]["status"] == findings["C"]["status"] == "not_mentioned"
    assert findings["Kubernetes"]["correction"] and findings["Kubernetes"]["resumeEvidence"] is None
    assert "technicalScore" not in result and "text" not in result
    structure = client.get(extraction(7, "pdf", "structure"), headers=headers()).json()
    assert "technicalScore" in structure and "findings" not in structure
    doc = response(2, "docx").json()
    assert doc["format"] == "docx" and doc["artifactSha256"] == sha256(artifacts[2, "docx"][1]).hexdigest()
    assert all(finding["status"] == "not_mentioned" for finding in doc["findings"])
    assert response(3).json()["reason"] == "no_text"
    assert response(group=EXTERNAL).json()["reason"] == "external_to_verify"
    stale = response(offer=OTHER_OFFER).json()
    assert stale["reason"] == "offer_version_changed" and "findings" not in stale
    assert response(group=NO_SUGGESTIONS).json()["reason"] == "no_verified_requirements"
    assert response(group=UNAVAILABLE).status_code == response(group=MALFORMED).status_code == 503
    assert response(group=OTHER_OFFER).status_code == 404
    assert response(auth={}).status_code == 401
    assert response(auth=headers(scopes=SCOPES)).status_code == 403
    assert response(auth=headers(tenant=str(UUID(int=306)), scopes=RELEVANCE_SCOPES)).status_code == 404
    assert response(offer="invalid").status_code == 422


checks = {"extraction": check, "structure": check_structure, "relevance": check_relevance}
scenario = sys.argv[1]
with httpx2.Client(transport=httpx2.MockTransport(upstream)) as resume:
    use_case = ExtractText(HttpResumeArtifacts(resume, "https://resume.example.invalid"), DocumentText())
    relevance = AssessRelevance(HttpRequirementEvidence(resume, "https://matching.example.invalid"))
    with TestClient(create_app(use_case, OidcVerifier(Keys(), ISSUER, AUDIENCE), relevance=relevance)) as ats:
        checks[scenario](ats)
print(f"ATS {scenario} HTTP acceptance passed.")
