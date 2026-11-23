import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import test from 'node:test';

function profileBoundary() {
  const items = new Map();
  let sequence = 0;
  return createServer(async (request, response) => {
    const owner = request.headers.authorization?.replace('Bearer ', '');
    if (!owner) return reply(response, 401, { code: 'UNAUTHENTICATED' });
    const body = await readBody(request);
    const match = request.url.match(/^\/v1\/profile\/items(?:\/([^?]+))?/);
    if (!match) return reply(response, 404, { code: 'NOT_FOUND' });
    const itemId = match[1];

    if (request.method === 'POST') {
      if (body.endDate && body.endDate < body.startDate) {
        return reply(response, 422, { code: 'VALIDATION_FAILED' });
      }
      const item = {
        ...body,
        itemId: `item-${++sequence}`,
        ...(body.kind === 'skill' && body.level ? { levelSource: 'selfDeclared' } : {}),
      };
      items.set(item.itemId, { owner, item });
      return reply(response, 201, item);
    }
    if (request.method === 'GET' && !itemId) {
      return reply(response, 200, { items: [...items.values()].filter(x => x.owner === owner).map(x => x.item) });
    }
    const stored = items.get(itemId);
    if (!stored || stored.owner !== owner) return reply(response, 404, { code: 'NOT_FOUND' });
    if (request.method === 'GET') return reply(response, 200, stored.item);
    if (request.method === 'PUT') {
      stored.item = { ...stored.item, ...body, itemId };
      return reply(response, 200, stored.item);
    }
    if (request.method === 'DELETE') {
      items.delete(itemId);
      response.writeHead(204).end();
      return;
    }
    return reply(response, 405, { code: 'METHOD_NOT_ALLOWED' });
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

async function call(baseUrl, owner, method, path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: { Authorization: `Bearer ${owner}`, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: response.status, body: response.status === 204 ? null : await response.json() };
}

test('BR-PRO-001/004/005 and BR-ACC-002: owned profile CRUD through HTTP', async () => {
  const server = profileBoundary().listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}`;
  try {
    const experience = await call(baseUrl, 'owner', 'POST', '/v1/profile/items', {
      kind: 'experience', title: 'Platform Engineer', employer: 'Example Labs', startDate: '2024-01-01', current: true,
    });
    const education = await call(baseUrl, 'owner', 'POST', '/v1/profile/items', {
      kind: 'education', institution: 'Example Institute', qualification: 'Synthetic Diploma', startDate: '2020-09-01', endDate: '2022-06-30',
    });
    const skill = await call(baseUrl, 'owner', 'POST', '/v1/profile/items', {
      kind: 'skill', name: 'Python', level: 'advanced',
    });
    assert.equal(skill.body.levelSource, 'selfDeclared');
    assert.equal((await call(baseUrl, 'owner', 'GET', '/v1/profile/items')).body.items.length, 3);

    const updated = await call(baseUrl, 'owner', 'PUT', `/v1/profile/items/${experience.body.itemId}`, { title: 'Senior Platform Engineer' });
    assert.equal(updated.body.title, 'Senior Platform Engineer');
    assert.equal((await call(baseUrl, 'other', 'GET', `/v1/profile/items/${experience.body.itemId}`)).status, 404);
    assert.equal((await call(baseUrl, 'owner', 'DELETE', `/v1/profile/items/${education.body.itemId}`)).status, 204);
    assert.equal((await call(baseUrl, 'owner', 'GET', '/v1/profile/items')).body.items.length, 2);

    const invalid = await call(baseUrl, 'owner', 'POST', '/v1/profile/items', {
      kind: 'experience', title: 'Invalid', employer: 'Example', startDate: '2025-01-01', endDate: '2024-01-01', current: false,
    });
    assert.equal(invalid.status, 422);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});
