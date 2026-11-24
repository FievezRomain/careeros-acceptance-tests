import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import test from 'node:test';

const digest = value => createHash('sha256').update(value).digest('hex');
const normalize = value => value.normalize('NFKC').trim().replace(/\s+/gu, ' ');
const materialHash = item => digest(JSON.stringify({
  title: normalize(item.title).toLocaleLowerCase('en-US'),
  employer: normalize(item.employer).toLocaleLowerCase('en-US'),
  description: normalize(item.description),
  location: normalize(item.location),
}));

function discoveryBoundary() {
  const searches = new Map();
  const observations = new Map();
  const runs = new Set();
  const retrievals = [];
  const events = [];
  const metrics = [];

  return {
    synchronize(event) {
      const current = searches.get(event.accountId);
      if (!current || current.version < event.version) searches.set(event.accountId, event);
    },
    run({ scheduledAt, idempotencyKey, source }) {
      if (runs.has(idempotencyKey)) return { replayed: true, events, metrics };
      runs.add(idempotencyKey);
      const instant = new Date(scheduledAt);
      const eligible = [...searches.values()].filter(search => {
        if (search.state !== 'active') return false;
        const hour = instant.getUTCHours().toString().padStart(2, '0');
        const minute = instant.getUTCMinutes().toString().padStart(2, '0');
        const localTime = `${hour}:${minute}`;
        return search.schedule.timezone === 'UTC'
          && search.schedule.windowStart <= localTime
          && localTime < search.schedule.windowEnd
          && search.lastRunDate !== scheduledAt.slice(0, 10);
      });
      const signatures = new Map();
      for (const search of eligible) {
        const bucket = signatures.get(search.searchSignature.signatureId) ?? [];
        bucket.push(search);
        signatures.set(search.searchSignature.signatureId, bucket);
      }

      for (const [signatureId, owners] of signatures) {
        retrievals.push(signatureId);
        let cursor = null;
        let pages = 0;
        do {
          const page = source.fetch({ signatureId, cursor });
          pages += 1;
          for (const item of page.items) {
            for (const owner of owners) {
              const key = `${owner.accountId}:${source.id}:${item.externalId}`;
              const hash = materialHash(item);
              const previous = observations.get(key);
              if (previous?.hash === hash) {
                previous.lastSeenAt = scheduledAt;
                continue;
              }
              const version = (previous?.version ?? 0) + 1;
              observations.set(key, {
                hash, version, lastSeenAt: scheduledAt, rawText: item.rawText,
                sourceUrl: item.sourceUrl, status: item.status ?? 'active',
              });
              if ((item.status ?? 'active') === 'active') {
                events.push({
                  type: 'job.opportunity-version-discovered.v1',
                  accountId: owner.accountId,
                  externalId: item.externalId,
                  version,
                  evidence: {
                    statedFields: ['title', 'employer', 'description', 'location'],
                    inferredFields: [], unknownFields: ['contractType', 'workMode'],
                  },
                });
              }
            }
          }
          cursor = page.nextCursor;
          metrics.push({
            source: source.id, cursor, page: pages, etag: page.etag,
            remaining: page.rateLimitRemaining, truncated: page.truncated === true,
          });
        } while (cursor !== null);
        for (const owner of owners) owner.lastRunDate = scheduledAt.slice(0, 10);
      }
      return { replayed: false, events, metrics };
    },
    observations,
    retrievals,
  };
}

const signature = {
  signatureId: digest('python|paris|remote|cdi'),
  targetRoles: ['python engineer'], locations: ['paris'], remotePolicy: 'remote',
  contractTypes: ['cdi'], exclusions: [],
};
const activeSearch = (accountId, overrides = {}) => ({
  accountId, tenantId: 'tenant-synthetic', criteriaVersionId: `${accountId}-v1`, version: 1,
  state: 'active', schedule: { timezone: 'UTC', windowStart: '08:00', windowEnd: '10:00' },
  searchSignature: signature, ...overrides,
});

test('BR-JOB-002..007: daily discovery is exhaustive, versioned and replay safe', () => {
  const boundary = discoveryBoundary();
  boundary.synchronize(activeSearch('owner-a'));
  boundary.synchronize(activeSearch('owner-b'));
  boundary.synchronize(activeSearch('owner-paused', { state: 'paused' }));
  boundary.synchronize(activeSearch('owner-late', {
    schedule: { timezone: 'UTC', windowStart: '10:00', windowEnd: '12:00' },
  }));
  const pages = [
    {
      items: [{
        externalId: 'gh-100', title: 'Python Engineer', employer: 'Example Labs',
        description: 'Build a synthetic service.', location: 'Paris',
        sourceUrl: 'https://boards.example.invalid/jobs/100',
        rawText: 'Python Engineer\nExample Labs\nBuild a synthetic service.',
      }],
      nextCursor: 'page-2', etag: 'etag-1', rateLimitRemaining: 99,
    },
    {
      items: [{
        externalId: 'gh-101', title: 'Senior Python Engineer', employer: 'Example Labs',
        description: 'Own a synthetic platform.', location: 'Remote', status: 'ignored',
        sourceUrl: 'https://boards.example.invalid/jobs/101',
        rawText: 'Senior Python Engineer\nExample Labs\nOwn a synthetic platform.',
      }],
      nextCursor: null, etag: 'etag-2', rateLimitRemaining: 98,
    },
  ];
  const source = { id: 'greenhouse:example', fetch: ({ cursor }) => pages[cursor ? 1 : 0] };

  const first = boundary.run({
    scheduledAt: '2026-11-24T08:30:00Z', idempotencyKey: 'daily-2026-11-24-0830', source,
  });
  const replay = boundary.run({
    scheduledAt: '2026-11-24T08:30:00Z', idempotencyKey: 'daily-2026-11-24-0830', source,
  });

  assert.equal(replay.replayed, true);
  assert.deepEqual(boundary.retrievals, [signature.signatureId]);
  assert.equal(first.metrics.length, 2);
  assert.equal(first.metrics.at(-1).cursor, null);
  assert.equal(first.events.length, 2);
  assert.ok(first.events.every(event => event.externalId === 'gh-100'));
  assert.deepEqual(first.events[0].evidence.unknownFields, ['contractType', 'workMode']);

  const unchanged = boundary.run({
    scheduledAt: '2026-11-25T08:30:00Z', idempotencyKey: 'daily-2026-11-25-0830', source,
  });
  assert.equal(unchanged.events.length, 2);
  assert.equal(boundary.observations.get('owner-a:greenhouse:example:gh-100').version, 1);

  pages[0].items[0] = {
    ...pages[0].items[0], description: 'Build a synthetic service and own reliability.',
    rawText: `${pages[0].items[0].rawText}\nOwn reliability.`,
  };
  const changed = boundary.run({
    scheduledAt: '2026-11-26T08:30:00Z', idempotencyKey: 'daily-2026-11-26-0830', source,
  });
  assert.equal(changed.events.length, 4);
  assert.equal(boundary.observations.get('owner-a:greenhouse:example:gh-100').version, 2);
  assert.equal(
    boundary.observations.get('owner-a:greenhouse:example:gh-100').rawText.endsWith('Own reliability.'),
    true,
  );
});
