import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import test from 'node:test';

function profileWebBoundary() {
  const items = new Map();
  let sequence = 0;

  return createServer(async (request, response) => {
    const session = request.headers.cookie?.match(/(?:^|; )careeros_session=([^;]+)/)?.[1];
    if (session !== 'synthetic-profile-owner') {
      return reply(response, 403, { code: 'PROFILE_ACCESS_DENIED' });
    }

    const body = await readBody(request);
    if (request.method === 'GET' && request.url === '/app/profile/items') {
      return reply(response, 200, { items: [...items.values()] });
    }

    if (request.method === 'POST' && request.url === '/app/profile/items') {
      if (hasInvalidDates(body)) {
        return reply(response, 422, { code: 'INVALID_DATE_RANGE' });
      }
      const item = {
        ...body,
        itemId: `00000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`,
        validationStatus: 'userConfirmed',
        ...(body.kind === 'skill' && body.level ? { levelSource: 'selfDeclared' } : {}),
      };
      items.set(item.itemId, item);
      return reply(response, 201, item);
    }

    const match = request.url?.match(/^\/app\/profile\/items\/([^/]+)$/);
    if (request.method === 'PUT' && match) {
      if (hasInvalidDates(body)) {
        return reply(response, 422, { code: 'INVALID_DATE_RANGE' });
      }
      const current = items.get(match[1]);
      if (!current) return reply(response, 404, { code: 'NOT_FOUND' });
      const updated = { ...current, ...body, itemId: match[1], validationStatus: 'userConfirmed' };
      items.set(match[1], updated);
      return reply(response, 200, updated);
    }

    return reply(response, 404, { code: 'NOT_FOUND' });
  });
}

function hasInvalidDates(body) {
  return body.current !== true && body.startDate && body.endDate && body.endDate < body.startDate;
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks)) : {};
}

function reply(response, status, body) {
  response.writeHead(status, {
    'Cache-Control': 'no-store',
    'Content-Type': 'application/json; charset=utf-8',
  });
  response.end(JSON.stringify(body));
}

async function call(baseUrl, session, method, path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      Cookie: `careeros_session=${session}`,
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: response.status, body: await response.json() };
}

async function withBoundary(run) {
  const server = profileWebBoundary().listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const { port } = server.address();
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}

test('BR-PRO-001/005 and BR-ACC-002: web onboarding creates and edits owned facts', async () => {
  await withBoundary(async baseUrl => {
    const session = 'synthetic-profile-owner';
    const experience = await call(baseUrl, session, 'POST', '/app/profile/items', {
      kind: 'experience',
      title: 'Platform Engineer',
      employer: 'Example Labs',
      startDate: '2024-01-01',
      current: true,
    });
    const education = await call(baseUrl, session, 'POST', '/app/profile/items', {
      kind: 'education',
      institution: 'Example Institute',
      qualification: 'Synthetic Diploma',
      startDate: '2020-09-01',
      endDate: '2022-06-30',
      current: false,
    });
    const skill = await call(baseUrl, session, 'POST', '/app/profile/items', {
      kind: 'skill',
      name: 'Python',
      level: 'advanced',
    });

    assert.equal(experience.status, 201);
    assert.equal(education.status, 201);
    assert.equal(skill.body.levelSource, 'selfDeclared');

    const corrected = await call(
      baseUrl,
      session,
      'PUT',
      `/app/profile/items/${experience.body.itemId}`,
      { ...experience.body, title: 'Senior Platform Engineer' },
    );
    assert.equal(corrected.body.title, 'Senior Platform Engineer');
    assert.equal(corrected.body.validationStatus, 'userConfirmed');

    const listed = await call(baseUrl, session, 'GET', '/app/profile/items');
    assert.equal(listed.body.items.length, 3);
  });
});

test('BR-PRO-004 and BR-ACC-002: invalid dates and denied sessions disclose no profile data', async () => {
  await withBoundary(async baseUrl => {
    const invalid = await call(baseUrl, 'synthetic-profile-owner', 'POST', '/app/profile/items', {
      kind: 'experience',
      title: 'Invalid range',
      employer: 'Example Labs',
      startDate: '2026-02-01',
      endDate: '2026-01-01',
      current: false,
    });
    assert.deepEqual(invalid, { status: 422, body: { code: 'INVALID_DATE_RANGE' } });

    const denied = await call(baseUrl, 'synthetic-no-profile-scope', 'GET', '/app/profile/items');
    assert.equal(denied.status, 403);
    assert.deepEqual(denied.body, { code: 'PROFILE_ACCESS_DENIED' });
    assert.doesNotMatch(JSON.stringify(denied), /access[_ -]?token|employer|qualification/i);
  });
});
