import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import test from 'node:test';

const { CAREEROS_DISCOVERY_GATEWAY_URL: gateway, CAREEROS_DISCOVERY_JOB_URL: jobs } = process.env;
const signature = {
  targetRoles: ['platform engineer'], locations: ['paris'],
  remotePolicy: 'any', contractTypes: ['cdi'],
};
const fixture = {
  protectedUrl: 'https://www.linkedin.com/jobs/view/123456',
  verifiedUrl: 'https://boards.greenhouse.io/synthetic/jobs/101',
  independentUrl: 'https://example.invalid/jobs/102',
};

async function call(base, path, token, { body, key = randomUUID(), status = 200 } = {}) {
  const response = await fetch(new URL(path, base), {
    method: body ? 'POST' : 'GET',
    headers: {
      Authorization: `Bearer ${token}`, 'Content-Type': 'application/json',
      'X-Correlation-ID': randomUUID(), 'Idempotency-Key': key,
    },
    body: body && JSON.stringify(body), signal: AbortSignal.timeout(15000),
  });
  assert.equal(response.status, status, `${path} returned ${response.status}`);
  return response.json();
}

test('BR-AI-002: gateway returns only validated raw search evidence', { skip: !gateway }, async () => {
  const result = await call(gateway, '/v1/capabilities/discover-job-links/invocations',
    process.env.CAREEROS_DISCOVERY_GATEWAY_TOKEN, {
      body: { capabilityVersion: '1.0', inputSchemaVersion: '1.0', input: signature },
    });
  assert.equal(result.outputSchemaVersion, '1.0');
  assert.equal(result.output.results.filter(item => item.url === fixture.protectedUrl).length, 1);
  assert.ok(result.output.results.every(item => item.url.startsWith('https://') && item.title && item.source));
  assert.equal(Object.hasOwn(result.output, 'answer'), false);
});

test('BR-JOB-002/003/004/006: retain and later promote an external link', { skip: !jobs }, async () => {
  const accountId = '00000000-0000-4000-8000-000000000001';
  const tenantId = '00000000-0000-4000-8000-000000000002';
  const discovery = process.env.CAREEROS_DISCOVERY_JOB_TOKEN;
  const owner = process.env.CAREEROS_DISCOVERY_OWNER_TOKEN;
  const other = process.env.CAREEROS_DISCOVERY_OTHER_TOKEN;
  await call(jobs, '/v1/internal/discovery/search-snapshots', discovery, {
    body: {
      eventId: randomUUID(), eventType: 'profile.match-relevant-change.v1', schemaVersion: '1.0',
      occurredAt: '2026-01-01T07:00:00Z', correlationId: randomUUID(), idempotencyKey: randomUUID(),
      accountId, tenantId, changedFields: ['searchSignature'], criteriaVersionId: randomUUID(),
      state: 'active', schedule: { timezone: 'UTC', windowStart: '08:00', windowEnd: '10:00' },
      searchSignature: { ...signature, signatureId: 'a'.repeat(64), exclusions: [] },
    },
  });
  const run = (day, key) => call(jobs, '/v1/internal/discovery/runs', discovery, {
    key, body: { scheduledAt: `2026-01-0${day}T08:30:00Z` },
  });
  const catalog = () => call(jobs, '/v1/jobs', owner);
  const key = randomUUID();
  assert.equal((await run(1, key)).created, 2);
  assert.equal((await run(1, key)).replayed, true);
  const { items } = await catalog();
  assert.equal(items.length, 2);
  assert.ok(items.some(item => item.source.reference === fixture.independentUrl));
  const partial = items.find(item => item.source.reference === fixture.protectedUrl);
  assert.ok(partial);
  assert.equal(partial.sourceAccess, 'external_to_verify');
  assert.equal(partial.resumeEligible, false);
  assert.ok(partial.evidence.unknownFields.includes('description'));
  assert.equal(partial.description, null);
  await call(jobs, `/v1/jobs/${partial.opportunityId}`, other, { status: 404 });

  assert.equal((await run(2, randomUUID())).changed, 1);
  const full = (await catalog()).items.find(item => item.groupId === partial.groupId);
  assert.equal(full.version, partial.version + 1);
  assert.equal(full.source.reference, fixture.verifiedUrl);
  assert.equal(full.sourceAccess, 'full_text');
  assert.equal(full.resumeEligible, true);
  const saved = await call(jobs, `/v1/jobs/${partial.opportunityId}`, owner);
  assert.equal(saved.sourceAccess, 'external_to_verify');
});
