import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import test from 'node:test';

function jobBoundary() {
  const records = new Map();
  let sequence = 0;
  return createServer(async (request, response) => {
    if (request.method !== 'POST' || request.url !== '/v1/jobs/manual') {
      return reply(response, 404, { code: 'NOT_FOUND' });
    }
    const owner = request.headers.authorization?.replace('Bearer ', '');
    if (!owner) return reply(response, 401, { code: 'UNAUTHENTICATED' });
    const key = request.headers['idempotency-key'];
    if (!key) return reply(response, 400, { code: 'IDEMPOTENCY_KEY_INVALID' });
    const body = await readBody(request);
    const allowed = ['title', 'employer', 'description', 'sourceReference', 'rawSource'];
    if (Object.keys(body).some(field => !allowed.includes(field))) {
      return reply(response, 422, { code: 'VALIDATION_FAILED' });
    }
    if (allowed.some(field => typeof body[field] !== 'string' || !body[field].trim())) {
      return reply(response, 422, { code: 'VALIDATION_FAILED' });
    }
    const fingerprint = createHash('sha256').update(JSON.stringify(body)).digest('hex');
    const idempotencyId = `${owner}:${key}`;
    const existing = records.get(idempotencyId);
    if (existing) {
      if (existing.fingerprint !== fingerprint) {
        return reply(response, 409, { code: 'IDEMPOTENCY_KEY_REUSED' });
      }
      return reply(response, 200, existing.opportunity);
    }
    const opportunity = {
      opportunityId: `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`,
      title: body.title,
      employer: body.employer,
      description: body.description,
      source: {
        kind: 'manual',
        reference: body.sourceReference,
        rawText: body.rawSource,
        capturedAt: '2026-11-24T08:00:00Z',
      },
      createdAt: '2026-11-24T08:00:00Z',
    };
    records.set(idempotencyId, { owner, fingerprint, opportunity });
    return reply(response, 201, opportunity);
  });
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks)) : {};
}

function reply(response, status, body) {
  response.writeHead(status, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify(body));
}

async function capture(baseUrl, owner, key, body) {
  const headers = { 'Content-Type': 'application/json', 'Idempotency-Key': key };
  if (owner) headers.Authorization = `Bearer ${owner}`;
  const response = await fetch(`${baseUrl}/v1/jobs/manual`, {
    method: 'POST', headers, body: JSON.stringify(body),
  });
  return { status: response.status, body: await response.json() };
}

const validDraft = {
  title: 'Platform Engineer',
  employer: 'Example Labs',
  description: 'Build a synthetic platform for demonstrative workloads.',
  sourceReference: 'https://jobs.example.invalid/platform-engineer',
  rawSource: 'Platform Engineer\nExample Labs\nBuild a synthetic platform.',
};

test('BR-JOB-001/002 and BR-ACC-001/002: owned manual capture preserves provenance', async () => {
  const server = jobBoundary().listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const created = await capture(baseUrl, 'owner-a', 'manual-capture-0001', validDraft);
    assert.equal(created.status, 201);
    assert.equal(created.body.source.kind, 'manual');
    assert.equal(created.body.source.reference, validDraft.sourceReference);
    assert.equal(created.body.source.rawText, validDraft.rawSource);
    assert.equal(created.body.source.capturedAt, '2026-11-24T08:00:00Z');
    assert.equal((await capture(baseUrl, 'owner-a', 'manual-capture-0001', validDraft)).status, 200);

    assert.equal((await capture(baseUrl, 'owner-a', 'invalid-capture-1', {
      ...validDraft, title: '',
    })).status, 422);
    assert.equal((await capture(baseUrl, null, 'unauthenticated-1', validDraft)).status, 401);
    assert.equal((await capture(baseUrl, 'owner-a', 'forged-owner-0001', {
      ...validDraft, ownerId: 'owner-b',
    })).status, 422);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});
