import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { after, before, test } from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const web = new URL('../../apps/web/', import.meta.url);
const requireWeb = createRequire(new URL('package.json', web));
const load = (name) => import(pathToFileURL(requireWeb.resolve(name)).href);
const id = (value) => `12345678-0000-4000-8000-${String(value).padStart(12, '0')}`;
const date = '2026-11-12T09:00:00Z';
const verified = {
  opportunityId: id(1), groupId: id(11), version: 2, title: 'Systems Engineer',
  employer: 'Example Studio', description: 'Maintain synthetic services.',
  location: 'Example City', sourceAccess: 'full_text', status: 'active',
  source: { kind: 'manual', reference: 'https://jobs.example.invalid/one', capturedAt: date },
  evidence: { statedFields: ['description'], inferredFields: [], unknownFields: ['workMode'] },
};
const linked = {
  ...verified, opportunityId: id(2), groupId: id(12), title: 'Platform Engineer',
  employer: null, description: null, location: null, sourceAccess: 'external_to_verify',
  source: { kind: 'open_web', reference: 'https://jobs.example.invalid/two', observedAt: date },
  evidence: { statedFields: ['title'], inferredFields: [], unknownFields: ['employer', 'description'] },
};
const finding = (number, statement, status, weight, earnedWeight, confirmedLevel) => ({
  requirementId: id(number), statement, status, weight, earnedWeight, confirmedLevel,
  factId: confirmedLevel === null ? null : id(number + 10), minimumLevel: 3,
  hardEligibility: status === 'missing',
});
const findings = [
  finding(21, 'Maintain Python services.', 'satisfied', 2, 2, 4),
  finding(22, 'Document incident response.', 'partial', 1, 0.5, 1),
  finding(23, 'Hold the required certification.', 'missing', 2, 0, 0),
  finding(24, 'Operate a messaging platform.', 'unknown', 1, null, null),
];
const recommendation = (job) => {
  const external = job.sourceAccess === 'external_to_verify';
  return {
    groupId: job.groupId, title: job.title, employer: job.employer,
    state: external ? 'unassessed' : 'inactive',
    reason: external ? 'external_to_verify' : 'hard_conflict',
    match: {
      opportunityVersionId: job.opportunityId, sourceAccess: job.sourceAccess,
      score: external ? null : 50, findings: external ? [] : findings,
      hardConflicts: external ? [] : [id(23)],
      explanation: {
        assessedRequirements: external ? 0 : 3, totalRequirements: external ? 0 : 4,
        assessedWeight: external ? 0 : 5, totalWeight: external ? 0 : 6,
        earnedWeight: external ? 0 : 2.5,
        uncertainty: external ? 'external_to_verify' : 'unconfirmed_profile_facts',
        scoreBounds: external ? null : { minimum: 42, maximum: 58 },
      },
      limitation: 'This score supports prioritization and does not guarantee an interview or employment.',
    },
  };
};

let vite, dom, react, render, fireEvent, within, createMemoryRouter, RouterProvider;
let routes, AuthProvider, JobsContext, HttpJobs;
before(async () => {
  const { JSDOM } = await load('jsdom');
  dom = new JSDOM('<!doctype html><html lang="en"><body></body></html>', { url: 'http://localhost/app' });
  globalThis.window = dom.window;
  globalThis.document = window.document;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  react = requireWeb('react');
  const testingLibrary = requireWeb('@testing-library/react');
  testingLibrary.configure({ asyncUtilTimeout: 10000 });
  ({ render, fireEvent, within } = testingLibrary);
  ({ createMemoryRouter, RouterProvider } = requireWeb('react-router-dom'));
  const { createServer } = await load('vite');
  vite = await createServer({
    root: fileURLToPath(web), configFile: false, esbuild: { jsx: 'automatic' },
    optimizeDeps: { noDiscovery: true },
    server: { middlewareMode: true, ws: false }, appType: 'custom',
  });
  ({ routes } = await vite.ssrLoadModule('/src/app/router.tsx'));
  ({ AuthProvider } = await vite.ssrLoadModule('/src/auth/auth-provider.tsx'));
  ({ JobsContext } = await vite.ssrLoadModule('/src/jobs/jobs-context.ts'));
  ({ HttpJobs } = await vite.ssrLoadModule('/src/jobs/jobs-http.ts'));
});

after(async () => {
  await vite?.close();
  dom?.window.close();
});

function open(path, { denied = false, stale = false } = {}) {
  const calls = [];
  const session = {
    restore: async () => ({ user: { subject: 'synthetic-owner', displayName: 'Synthetic Owner' } }),
    onSessionChanged: () => () => {},
    getAccessToken: async () => 'synthetic-token',
  };
  const jobs = new HttpJobs('https://job.example.invalid', 'https://match.example.invalid', session,
    async (url, options) => {
      const request = new Request(url, options);
      assert.equal(request.headers.get('authorization'), 'Bearer synthetic-token');
      const { hostname, pathname } = new URL(request.url);
      calls.push([hostname, pathname]);
      if (denied) return Response.json(verified, { status: 403 });
      if (pathname === '/v1/jobs') return Response.json({ items: [linked, verified], page: 1, pageSize: 20, total: 2 });
      if (pathname === '/v1/recommendations') return Response.json({
        items: [{ ...recommendation(verified), state: 'active', reason: 'qualified' }, recommendation(linked)],
      });
      if (pathname === `/v1/jobs/${verified.opportunityId}`) return Response.json(verified);
      if (pathname === `/v1/jobs/${linked.opportunityId}`) return Response.json(linked);
      if (pathname === `/v1/recommendations/${verified.groupId}`) {
        const result = recommendation(verified);
        if (stale) result.match.opportunityVersionId = id(100);
        return Response.json(result);
      }
      if (pathname === `/v1/recommendations/${linked.groupId}`) return Response.json(recommendation(linked));
      return new Response(null, { status: 404 });
    });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const view = render(react.createElement(AuthProvider, { sessionPort: session },
    react.createElement(JobsContext.Provider, { value: jobs }, react.createElement(RouterProvider, { router }))));
  return { view, calls, main: () => within(view.getByRole('main')) };
}

test('V1-026 preserves recommendation order and renders source, findings and score limitations', async () => {
  const { view, main, calls } = open('/app/jobs');
  try {
    await view.findByRole('link', { name: verified.title });
    assert.deepEqual(main().getAllByRole('listitem').map((row) => row.querySelector('a').textContent),
      [verified.title, linked.title]);
    fireEvent.click(main().getByRole('link', { name: verified.title }));
    await view.findByText('Maintain Python services.');
    for (const label of ['Satisfied', 'Partially satisfied', 'Missing', 'Unknown', 'Hard eligibility conflict']) {
      assert.ok(main().getByText(label, { exact: true }));
    }
    assert.match(view.container.textContent, /3 of 4 requirements assessed/);
    assert.match(view.container.textContent, /42–58%/);
    assert.match(view.container.textContent, /does not guarantee an interview/);
    assert.equal(main().getByRole('link', { name: 'View source' }).href, verified.source.reference);
    assert.deepEqual(calls.slice(-2), [['job.example.invalid', `/v1/jobs/${verified.opportunityId}`],
      ['match.example.invalid', `/v1/recommendations/${verified.groupId}`]]);
    fireEvent.click(main().getByRole('link', { name: 'Browse catalog' }));
    fireEvent.click(await view.findByRole('link', { name: linked.title }));
    await view.findByText('Score unavailable');
    assert.match(view.container.textContent, /External to verify/);
    assert.match(view.container.textContent, /employer, description/i);
    assert.doesNotMatch(view.container.textContent, /Maintain Python services/);
  } finally {
    view.unmount();
  }
});

test('V1-026 discloses no denied response or explanation for a different version', async () => {
  const denied = open(`/app/jobs/${verified.opportunityId}`, { denied: true });
  try {
    await denied.view.findByRole('alert');
    assert.match(denied.view.container.textContent, /Access to this opportunity was denied/);
    assert.doesNotMatch(denied.view.container.textContent, /Systems Engineer|Example Studio|synthetic-token/);
    assert.equal(denied.calls.length, 1);
  } finally {
    denied.view.unmount();
  }
  const stale = open(`/app/jobs/${verified.opportunityId}`, { stale: true });
  try {
    await stale.view.findByText('No match explanation for this version yet.');
    assert.ok(stale.main().getByRole('heading', { name: verified.title }));
    assert.doesNotMatch(stale.view.container.textContent, /Maintain Python services|50%/);
  } finally {
    stale.view.unmount();
  }
});
