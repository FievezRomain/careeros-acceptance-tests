"""Exercise the ATS public API and its delegation to the final artifact route."""

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
from careeros_ats.adapters.oidc import OidcVerifier
from careeros_ats.adapters.resume import HttpResumeArtifacts
from careeros_ats.application.extraction import ExtractText

RESUME = UUID(int=301)
OWNER = str(UUID(int=302))
TENANT = str(UUID(int=303))
CORRELATION = str(UUID(int=304))
ISSUER = "https://identity.example.invalid"
AUDIENCE = "careeros-acceptance"
SCOPES = "ats:extractions:read resume:versions:read"
PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def pdf(text):
    stream = BytesIO()
    canvas = Canvas(stream)
    if text:
        canvas.drawString(72, 720, text)
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


def extraction(number, kind):
    return f"/v1/resumes/{RESUME}/versions/{number}/artifacts/{kind}/extraction"


artifacts = {
    (1, "pdf"): (PDF, pdf("Final PDF version one")),
    (2, "pdf"): (PDF, pdf("Final PDF version two")),
    (2, "docx"): (DOCX, docx()),
    (3, "pdf"): (PDF, pdf("")),
    (3, "docx"): (DOCX, b"unreadable synthetic file"),
}
reads = []


def upstream(request):
    claims = jwt.decode(
        request.headers["Authorization"].removeprefix("Bearer "),
        key.public_key(), algorithms=["RS256"], issuer=ISSUER, audience=AUDIENCE,
    )
    assert request.headers["X-Correlation-ID"] == CORRELATION
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


with httpx2.Client(transport=httpx2.MockTransport(upstream)) as resume:
    use_case = ExtractText(HttpResumeArtifacts(resume, "https://resume.example.invalid"), DocumentText())
    with TestClient(create_app(use_case, OidcVerifier(Keys(), ISSUER, AUDIENCE))) as ats:
        check(ats)
print("V1-030 HTTP acceptance passed for exact owned artifacts, extraction and inconclusive results.")
