import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import test from 'node:test';

function profileBoundary() {
  const items = new Map();
  const snapshots = new Map();
  const idempotency = new Map();
  let itemSequence = 0;
  let snapshotSequence = 0;

  return createServer(async (request, response) => {
    const owner = request.headers.authorization?.replace('Bearer ', '');
    if (!owner) return reply(response, 401, { code: 'UNAUTHENTICATED' });

    const body = await readBody(request);
    const itemMatch = request.url.match(/^\/v1\/profile\/items(?:\/([^/]+))?(?:\/(confirmation))?$/);
    const snapshotMatch = request.url.match(/^\/v1\/profile\/snapshots(?:\/([^/]+))?$/);

    if (itemMatch) {
      const itemId = itemMatch[1];
      const action = itemMatch[2];

      if (request.method === 'POST' && !itemId) {
        if (body.provenance?.origin === 'userCorrection') {
          return reply(response, 422, { code: 'VALIDATION_FAILED' });
        }
        const now = '2026-01-01T00:00:00Z';
        const origin = body.provenance?.origin ?? 'directEntry';
        const item = {
          ...body,
          itemId: uuid(++itemSequence),
          provenance: {
            origin,
            ...(body.provenance?.sourceId ? { sourceId: body.provenance.sourceId } : {}),
            recordedAt: now,
          },
          validationStatus: origin === 'directEntry' ? 'userConfirmed' : 'unconfirmed',
          createdAt: now,
          updatedAt: now,
        };
        items.set(item.itemId, { owner, item });
        return reply(response, 201, item);
      }

      const stored = items.get(itemId);
      if (!stored || stored.owner !== owner) return reply(response, 404, { code: 'NOT_FOUND' });

      if (request.method === 'PUT' && action === 'confirmation') {
        stored.item = { ...stored.item, validationStatus: 'userConfirmed', updatedAt: '2026-01-02T00:00:00Z' };
        return reply(response, 200, stored.item);
      }
      if (request.method === 'PUT' && !action) {
        stored.item = {
          ...body,
          itemId,
          provenance: { origin: 'userCorrection', sourceId: itemId, recordedAt: '2026-01-03T00:00:00Z' },
          validationStatus: 'userConfirmed',
          createdAt: stored.item.createdAt,
          updatedAt: '2026-01-03T00:00:00Z',
        };
        return reply(response, 200, stored.item);
      }
      if (request.method === 'GET') return reply(response, 200, stored.item);
      return reply(response, 405, { code: 'METHOD_NOT_ALLOWED' });
    }

    if (snapshotMatch) {
      const snapshotId = snapshotMatch[1];
      if (request.method === 'POST' && !snapshotId) {
        const key = request.headers['idempotency-key'];
        if (!key) return reply(response, 400, { code: 'IDEMPOTENCY_KEY_REQUIRED' });
        const fingerprint = createHash('sha256').update(JSON.stringify(body)).digest('hex');
        const previous = idempotency.get(`${owner}:${key}`);
        if (previous) {
          if (previous.fingerprint !== fingerprint) return reply(response, 409, { code: 'IDEMPOTENCY_KEY_REUSED' });
          return reply(response, 201, previous.snapshot);
        }
        const snapshot = {
          snapshotId: uuid(++snapshotSequence),
          createdAt: '2026-01-02T12:00:00Z',
          items: structuredClone([...items.values()].filter(entry => entry.owner === owner).map(entry => entry.item)),
        };
        snapshots.set(snapshot.snapshotId, { owner, snapshot });
        idempotency.set(`${owner}:${key}`, { fingerprint, snapshot });
        return reply(response, 201, snapshot);
      }

      const stored = snapshots.get(snapshotId);
      if (!stored || stored.owner !== owner) return reply(response, 404, { code: 'NOT_FOUND' });
      if (request.method === 'GET') return reply(response, 200, stored.snapshot);
      return reply(response, 405, { code: 'METHOD_NOT_ALLOWED' });
    }

    return reply(response, 404, { code: 'NOT_FOUND' });
  });
}

function uuid(sequence) {
  return `00000000-0000-4000-8000-${String(sequence).padStart(12, '0')}`;
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

async function call(baseUrl, owner, method, path, body, headers = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: { Authorization: `Bearer ${owner}`, 'Content-Type': 'application/json', ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: response.status, body: await response.json() };
}

test('BR-PRO-002/003: imported and generated facts remain unconfirmed until owner approval', async () => {
  await withBoundary(async baseUrl => {
    const imported = await call(baseUrl, 'owner', 'POST', '/v1/profile/items', {
      kind: 'experience',
      title: 'Platform Engineer',
      employer: 'Example Labs',
      startDate: '2024-01-01',
      current: true,
      provenance: { origin: 'resumeImport', sourceId: 'synthetic-resume-001' },
    });
    const generated = await call(baseUrl, 'owner', 'POST', '/v1/profile/items', {
      kind: 'skill',
      name: 'Python',
      provenance: { origin: 'generatedSuggestion', sourceId: 'synthetic-suggestion-001' },
    });

    assert.equal(imported.status, 201);
    assert.deepEqual(imported.body.provenance, {
      origin: 'resumeImport', sourceId: 'synthetic-resume-001', recordedAt: '2026-01-01T00:00:00Z',
    });
    assert.equal(imported.body.validationStatus, 'unconfirmed');
    assert.equal(generated.body.provenance.origin, 'generatedSuggestion');
    assert.equal(generated.body.validationStatus, 'unconfirmed');

    const confirmed = await call(
      baseUrl,
      'owner',
      'PUT',
      `/v1/profile/items/${imported.body.itemId}/confirmation`,
    );
    assert.equal(confirmed.status, 200);
    assert.equal(confirmed.body.validationStatus, 'userConfirmed');
  });
});

test('BR-PRO-006: a live correction cannot rewrite an immutable owned snapshot', async () => {
  await withBoundary(async baseUrl => {
    const imported = await call(baseUrl, 'owner', 'POST', '/v1/profile/items', {
      kind: 'experience',
      title: 'Platform Engineer',
      employer: 'Example Labs',
      startDate: '2024-01-01',
      current: true,
      provenance: { origin: 'resumeImport', sourceId: 'synthetic-resume-001' },
    });
    await call(baseUrl, 'owner', 'PUT', `/v1/profile/items/${imported.body.itemId}/confirmation`);

    const createdSnapshot = await call(
      baseUrl,
      'owner',
      'POST',
      '/v1/profile/snapshots',
      {},
      { 'Idempotency-Key': 'synthetic-snapshot-001' },
    );
    assert.equal(createdSnapshot.status, 201);

    const corrected = await call(baseUrl, 'owner', 'PUT', `/v1/profile/items/${imported.body.itemId}`, {
      kind: 'experience',
      title: 'Senior Platform Engineer',
      employer: 'Example Labs',
      startDate: '2024-01-01',
      current: true,
    });
    assert.equal(corrected.body.provenance.origin, 'userCorrection');
    assert.equal(corrected.body.validationStatus, 'userConfirmed');

    const snapshot = await call(
      baseUrl,
      'owner',
      'GET',
      `/v1/profile/snapshots/${createdSnapshot.body.snapshotId}`,
    );
    assert.equal(snapshot.body.items[0].title, 'Platform Engineer');
    assert.equal(snapshot.body.items[0].provenance.origin, 'resumeImport');
    assert.equal(snapshot.body.items[0].validationStatus, 'userConfirmed');

    const concealed = await call(
      baseUrl,
      'other-owner',
      'GET',
      `/v1/profile/snapshots/${createdSnapshot.body.snapshotId}`,
    );
    assert.equal(concealed.status, 404);
  });
});

async function withBoundary(run) {
  const server = profileBoundary().listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const { port } = server.address();
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}
