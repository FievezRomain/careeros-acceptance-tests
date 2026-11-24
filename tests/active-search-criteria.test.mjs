import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import test from 'node:test';

const defaultSchedule = Object.freeze({
  timezone: 'Europe/Paris',
  windowStart: '08:00',
  windowEnd: '10:00',
});

function searchBoundary() {
  const versions = new Map();
  const currentByOwner = new Map();
  let sequence = 0;

  return createServer(async (request, response) => {
    const owner = request.headers.authorization?.replace('Bearer ', '');
    if (!owner) return reply(response, 401, { code: 'UNAUTHENTICATED' });
    const body = await readBody(request);

    if (request.method === 'PUT' && request.url === '/v1/profile/search-criteria') {
      const error = validate(body);
      if (error) return reply(response, 422, { code: error });
      const snapshot = createSnapshot(++sequence, owner, body, 'active');
      versions.set(snapshot.criteriaVersionId, { owner, snapshot });
      currentByOwner.set(owner, snapshot);
      return reply(response, 200, snapshot);
    }

    const transition = request.url?.match(/^\/v1\/profile\/search-criteria\/(pause|resume)$/);
    if (request.method === 'POST' && transition) {
      const current = currentByOwner.get(owner);
      if (!current) return reply(response, 404, { code: 'NOT_FOUND' });
      const snapshot = {
        ...structuredClone(current),
        criteriaVersionId: uuid(++sequence),
        version: current.version + 1,
        state: transition[1] === 'pause' ? 'paused' : 'active',
      };
      versions.set(snapshot.criteriaVersionId, { owner, snapshot });
      currentByOwner.set(owner, snapshot);
      return reply(response, 200, snapshot);
    }

    if (request.method === 'GET' && request.url === '/v1/profile/search-criteria') {
      const current = currentByOwner.get(owner);
      return current ? reply(response, 200, current) : reply(response, 404, { code: 'NOT_FOUND' });
    }

    const version = request.url?.match(/^\/v1\/profile\/search-criteria\/versions\/([^/]+)$/);
    if (request.method === 'GET' && version) {
      const stored = versions.get(version[1]);
      return stored?.owner === owner
        ? reply(response, 200, stored.snapshot)
        : reply(response, 404, { code: 'NOT_FOUND' });
    }

    if (request.method === 'POST' && request.url === '/v1/profile/change-impact') {
      const relevant = new Set([
        'targetRoles', 'skills', 'experiences', 'locations', 'workPreferences', 'searchCriteria',
      ]);
      return reply(response, 200, {
        requestsRematch: body.changedFields.some(field => relevant.has(field)),
      });
    }

    return reply(response, 404, { code: 'NOT_FOUND' });
  });
}

function createSnapshot(sequence, owner, body, state) {
  const criteria = {
    targetRoles: normalize(body.targetRoles),
    locations: normalize(body.locations),
    remotePolicy: body.remotePolicy,
    contractTypes: normalize(body.contractTypes),
    exclusions: normalize(body.exclusions),
    minimumScore: body.minimumScore,
  };
  const searchSignature = {
    targetRoles: criteria.targetRoles,
    locations: criteria.locations,
    remotePolicy: criteria.remotePolicy,
    contractTypes: criteria.contractTypes,
    exclusions: criteria.exclusions,
  };
  return {
    criteriaVersionId: uuid(sequence),
    version: (body.previousVersion ?? 0) + 1,
    state,
    criteria,
    schedule: body.schedule ?? defaultSchedule,
    searchSignature: {
      signatureId: createHash('sha256').update(JSON.stringify(searchSignature)).digest('hex'),
      ...searchSignature,
    },
    ownerReference: createHash('sha256').update(owner).digest('hex').slice(0, 16),
  };
}

function normalize(values) {
  return [...new Set(values.map(value => value.normalize('NFKC').trim().replaceAll(/\s+/g, ' ').toLowerCase()))]
    .sort();
}

function validate(body) {
  if (!body.targetRoles?.length || !body.locations?.length) return 'SEARCH_DIMENSION_REQUIRED';
  if (!['remote', 'hybrid', 'onsite', 'any'].includes(body.remotePolicy)) return 'REMOTE_POLICY_INVALID';
  if (!body.contractTypes?.length || !body.exclusions) return 'SEARCH_DIMENSION_REQUIRED';
  if (!Number.isInteger(body.minimumScore) || body.minimumScore < 0 || body.minimumScore > 100) {
    return 'MINIMUM_SCORE_INVALID';
  }
  const schedule = body.schedule ?? defaultSchedule;
  if (!['Europe/Paris', 'UTC'].includes(schedule.timezone)) return 'TIMEZONE_INVALID';
  if (schedule.windowStart >= schedule.windowEnd) return 'SEARCH_WINDOW_INVALID';
  return undefined;
}

function renderSettings(snapshot) {
  return [
    snapshot.state === 'active' ? 'Automatic search active' : 'Automatic search paused',
    `${snapshot.schedule.timezone} ${snapshot.schedule.windowStart}–${snapshot.schedule.windowEnd}`,
    `Criteria version ${snapshot.version}`,
    'Relevant criteria changes request rematching',
  ].join(' · ');
}

async function call(baseUrl, owner, method, path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      ...(owner ? { Authorization: `Bearer ${owner}` } : {}),
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: response.status, body: await response.json() };
}

function criteria(overrides = {}) {
  return {
    targetRoles: ['Platform Engineer'],
    locations: ['Paris', 'Remote Europe'],
    remotePolicy: 'hybrid',
    contractTypes: ['CDI'],
    exclusions: ['internship'],
    minimumScore: 72,
    ...overrides,
  };
}

test('BR-PRO-008: criteria state, schedule and immutable versions remain visible', async () => {
  await withBoundary(async baseUrl => {
    const first = await call(baseUrl, 'owner-a', 'PUT', '/v1/profile/search-criteria', criteria());
    assert.equal(first.status, 200);
    assert.deepEqual(first.body.schedule, defaultSchedule);
    assert.match(renderSettings(first.body), /active.*Europe\/Paris.*version 1.*rematching/i);

    const changed = await call(baseUrl, 'owner-a', 'PUT', '/v1/profile/search-criteria', criteria({
      targetRoles: ['Senior Platform Engineer'],
      previousVersion: first.body.version,
    }));
    const previous = await call(
      baseUrl, 'owner-a', 'GET',
      `/v1/profile/search-criteria/versions/${first.body.criteriaVersionId}`,
    );
    assert.equal(changed.body.version, 2);
    assert.deepEqual(previous.body.criteria.targetRoles, ['platform engineer']);
  });
});

test('BR-PRO-008 and BR-ACC-002: pause, resume, validation and ownership fail closed', async () => {
  await withBoundary(async baseUrl => {
    const created = await call(baseUrl, 'owner-a', 'PUT', '/v1/profile/search-criteria', criteria());
    const paused = await call(baseUrl, 'owner-a', 'POST', '/v1/profile/search-criteria/pause');
    const resumed = await call(baseUrl, 'owner-a', 'POST', '/v1/profile/search-criteria/resume');
    assert.equal(paused.body.state, 'paused');
    assert.equal(resumed.body.state, 'active');

    const anonymous = await call(baseUrl, undefined, 'GET', '/v1/profile/search-criteria');
    const concealed = await call(
      baseUrl, 'owner-b', 'GET',
      `/v1/profile/search-criteria/versions/${created.body.criteriaVersionId}`,
    );
    const invalid = await call(baseUrl, 'owner-a', 'PUT', '/v1/profile/search-criteria', criteria({
      schedule: { timezone: 'Invalid/Zone', windowStart: '10:00', windowEnd: '08:00' },
    }));
    assert.equal(anonymous.status, 401);
    assert.deepEqual(concealed, { status: 404, body: { code: 'NOT_FOUND' } });
    assert.equal(invalid.status, 422);
  });
});

test('BR-PRO-010: exact normalized signatures share retrieval without weakening criteria', async () => {
  await withBoundary(async baseUrl => {
    const first = await call(baseUrl, 'owner-a', 'PUT', '/v1/profile/search-criteria', criteria());
    const second = await call(baseUrl, 'owner-b', 'PUT', '/v1/profile/search-criteria', criteria({
      targetRoles: ['  platform   engineer '],
      locations: ['remote europe', 'PARIS'],
      contractTypes: ['cdi'],
      minimumScore: 91,
    }));
    assert.equal(first.body.searchSignature.signatureId, second.body.searchSignature.signatureId);
    assert.equal(first.body.criteria.minimumScore, 72);
    assert.equal(second.body.criteria.minimumScore, 91);
    assert.doesNotMatch(JSON.stringify(first.body.searchSignature), /email|phone|experience|minimumScore/i);
  });
});

test('BR-PRO-009: only match-relevant changes request rematching', async () => {
  await withBoundary(async baseUrl => {
    for (const field of ['targetRoles', 'skills', 'experiences', 'locations', 'workPreferences', 'searchCriteria']) {
      const result = await call(
        baseUrl, 'owner-a', 'POST', '/v1/profile/change-impact', { changedFields: [field] },
      );
      assert.equal(result.body.requestsRematch, true);
    }
    for (const field of ['contactDetails', 'displayName', 'avatar']) {
      const result = await call(
        baseUrl, 'owner-a', 'POST', '/v1/profile/change-impact', { changedFields: [field] },
      );
      assert.equal(result.body.requestsRematch, false);
    }
  });
});

function uuid(sequence) {
  return `00000000-0000-4000-8000-${String(sequence).padStart(12, '0')}`;
}

async function readBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return chunks.length ? JSON.parse(Buffer.concat(chunks)) : {};
}

function reply(response, status, body) {
  response.writeHead(status, { 'Cache-Control': 'no-store', 'Content-Type': 'application/json' });
  response.end(JSON.stringify(body));
}

async function withBoundary(run) {
  const server = searchBoundary().listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const { port } = server.address();
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}
