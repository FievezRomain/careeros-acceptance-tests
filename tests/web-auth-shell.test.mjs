import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import test from 'node:test';

function webBoundary() {
  return createServer((request, response) => {
    if (request.url === '/sign-in') {
      return reply(response, 200, '<main><h1>Sign in to CareerOS</h1></main>');
    }
    if (request.url?.startsWith('/app')) {
      const session = request.headers.cookie?.match(/(?:^|; )careeros_session=([^;]+)/)?.[1];
      if (session !== 'synthetic-valid-session') {
        response.writeHead(302, {
          'Cache-Control': 'no-store',
          Location: `/sign-in?returnTo=${encodeURIComponent(request.url)}`,
        });
        return response.end();
      }
      return reply(
        response,
        200,
        '<main><h1>CareerOS workspace</h1><nav>Profile Jobs Resumes Applications</nav></main>',
        { 'Cache-Control': 'no-store' },
      );
    }
    return reply(response, 404, '<main>Not found</main>');
  });
}

function reply(response, status, body, headers = {}) {
  response.writeHead(status, { 'Content-Type': 'text/html; charset=utf-8', ...headers });
  response.end(body);
}

test('BR-ACC-001: anonymous and invalid sessions cannot render the protected shell', async () => {
  await withBoundary(async baseUrl => {
    for (const headers of [{}, { Cookie: 'careeros_session=synthetic-invalid-session' }]) {
      const response = await fetch(`${baseUrl}/app/profile`, { headers, redirect: 'manual' });
      assert.equal(response.status, 302);
      assert.equal(response.headers.get('location'), '/sign-in?returnTo=%2Fapp%2Fprofile');
      assert.equal(response.headers.get('cache-control'), 'no-store');
      const body = await response.text();
      assert.equal(body, '');
      assert.doesNotMatch(`${response.url}${body}`, /token|profile data|application data/i);
    }
  });
});

test('BR-ACC-001: a restored session renders protected navigation without token disclosure', async () => {
  await withBoundary(async baseUrl => {
    const response = await fetch(`${baseUrl}/app`, {
      headers: { Cookie: 'careeros_session=synthetic-valid-session' },
    });
    const body = await response.text();

    assert.equal(response.status, 200);
    assert.equal(response.headers.get('cache-control'), 'no-store');
    assert.match(body, /CareerOS workspace/);
    assert.match(body, /Profile Jobs Resumes Applications/);
    assert.doesNotMatch(`${response.url}${body}`, /access[_ -]?token|refresh[_ -]?token/i);
  });
});

async function withBoundary(run) {
  const server = webBoundary().listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const { port } = server.address();
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
}
