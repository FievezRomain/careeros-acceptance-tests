import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import test from 'node:test';

const normalize = value => value.normalize('NFKC').trim().replace(/\s+/gu, ' ');
const identity = value => normalize(value).toLocaleLowerCase('en-US');
const digest = value => createHash('sha256').update(value).digest('hex');

function jobBoundary() {
  const records = [];
  let sequence = 0;
  return createServer(async (request, response) => {
    const owner = request.headers.authorization?.replace('Bearer ', '');
    if (!owner) return reply(response, 401, { code: 'UNAUTHENTICATED' });

    if (request.method === 'POST' && request.url === '/v1/jobs/manual') {
      const body = await readBody(request);
      const title = normalize(body.title);
      const employer = normalize(body.employer);
      const description = normalize(body.description);
      const automaticKey = digest(`${identity(title)}\u001f${identity(employer)}`);
      const contentKey = digest([
        identity(title), identity(employer), identity(description), normalize(body.rawSource),
      ].join('\u001f'));
      const groupingKey = body.forceSeparate
        ? digest(`${automaticKey}\u001fseparate\u001f${++sequence}`)
        : automaticKey;
      const groupRecords = records.filter(record => (
        record.owner === owner && record.groupingKey === groupingKey
      ));
      const duplicate = groupRecords.find(record => record.contentKey === contentKey);
      if (duplicate) return reply(response, 200, duplicate.opportunity);

      const groupId = groupRecords[0]?.opportunity.groupId
        ?? `10000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`;
      const opportunity = {
        opportunityId: `20000000-0000-4000-8000-${String(++sequence).padStart(12, '0')}`,
        groupId,
        version: groupRecords.length + 1,
        title,
        employer,
        description,
        source: {
          kind: 'manual', reference: body.sourceReference, rawText: body.rawSource,
          capturedAt: '2026-11-24T08:00:00Z',
        },
        evidence: {
          statedFields: ['title', 'employer', 'description'],
          inferredFields: [],
          unknownFields: ['location', 'contractType', 'workMode'],
        },
        createdAt: '2026-11-24T08:00:00Z',
      };
      records.push({ owner, groupingKey, contentKey, opportunity });
      return reply(response, 201, opportunity);
    }

    if (request.method === 'GET' && request.url?.startsWith('/v1/jobs?')) {
      const latest = new Map();
      for (const record of records.filter(candidate => candidate.owner === owner)) {
        const current = latest.get(record.opportunity.groupId);
        if (!current || current.version < record.opportunity.version) {
          latest.set(record.opportunity.groupId, record.opportunity);
        }
      }
      const items = [...latest.values()];
      return reply(response, 200, { items, page: 1, pageSize: 20, total: items.length });
    }

    const match = request.url?.match(/^\/v1\/jobs\/([^/?]+)$/u);
    if (request.method === 'GET' && match) {
      const record = records.find(candidate => (
        candidate.owner === owner && candidate.opportunity.opportunityId === match[1]
      ));
      return record
        ? reply(response, 200, record.opportunity)
        : reply(response, 404, { code: 'OPPORTUNITY_NOT_FOUND' });
    }
    return reply(response, 404, { code: 'NOT_FOUND' });
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

async function request(baseUrl, owner, path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${owner}`,
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });
  return { status: response.status, body: await response.json() };
}

const draft = {
  title: '  Platform\u00a0Engineer  ',
  employer: 'Example   Labs',
  description: 'Build a synthetic platform.',
  sourceReference: 'https://jobs.example.invalid/platform-engineer',
  rawSource: 'Platform Engineer\nExample Labs\nBuild a synthetic platform.',
};

test('BR-JOB-003/004/006: catalog groups, versions and isolates normalized opportunities', async () => {
  const server = jobBoundary().listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const { port } = server.address();
  const baseUrl = `http://127.0.0.1:${port}`;
  const capture = (owner, body) => request(baseUrl, owner, '/v1/jobs/manual', {
    method: 'POST', body: JSON.stringify(body),
  });
  try {
    const first = await capture('owner-a', draft);
    const duplicate = await capture('owner-a', {
      ...draft, title: 'platform engineer', employer: 'example labs',
    });
    assert.equal(first.status, 201);
    assert.equal(duplicate.status, 200);
    assert.equal(duplicate.body.opportunityId, first.body.opportunityId);
    assert.equal(first.body.title, 'Platform Engineer');
    assert.equal(first.body.employer, 'Example Labs');

    const changed = await capture('owner-a', {
      ...draft,
      description: 'Build a synthetic platform and own reliability.',
      rawSource: `${draft.rawSource}\nOwn reliability.`,
    });
    assert.equal(changed.body.groupId, first.body.groupId);
    assert.equal(changed.body.version, 2);
    assert.equal((await request(
      baseUrl, 'owner-a', `/v1/jobs/${first.body.opportunityId}`,
    )).body.version, 1);

    const separated = await capture('owner-a', { ...draft, forceSeparate: true });
    assert.notEqual(separated.body.groupId, first.body.groupId);
    await capture('owner-b', draft);

    const catalog = await request(baseUrl, 'owner-a', '/v1/jobs?page=1&pageSize=20');
    assert.equal(catalog.status, 200);
    assert.equal(catalog.body.total, 2);
    assert.deepEqual(catalog.body.items[0].evidence, {
      statedFields: ['title', 'employer', 'description'],
      inferredFields: [],
      unknownFields: ['location', 'contractType', 'workMode'],
    });
    assert.equal((await request(
      baseUrl, 'owner-b', `/v1/jobs/${first.body.opportunityId}`,
    )).status, 404);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});
