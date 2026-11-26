import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { createInterface } from 'node:readline';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const fixture = fileURLToPath(new URL('./open-web-fixture.py', import.meta.url));
const servers = [];

async function start(service, role, env = {}) {
  const directory = join(root, 'services', service);
  const python = process.platform === 'win32' ? ['Scripts', 'python.exe'] : ['bin', 'python'];
  const processHandle = spawn(join(directory, '.venv', ...python), [fixture, role], {
    cwd: directory, env: { ...process.env, ...env }, stdio: ['ignore', 'pipe', 'inherit'],
  });
  servers.push(processHandle);
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${service} fixture did not start`)), 20000);
    processHandle.once('error', reject);
    processHandle.once('exit', code => {
      clearTimeout(timer);
      reject(new Error(`${service} fixture exited with code ${code}`));
    });
    createInterface({ input: processHandle.stdout }).on('line', async line => {
      const match = /^fixture-port=(\d+)$/.exec(line);
      if (match) {
        const base = `http://127.0.0.1:${match[1]}`;
        for (let attempt = 0; attempt < 100; attempt += 1) {
          try {
            if ((await fetch(`${base}/health/live`)).ok) {
              clearTimeout(timer);
              resolve(base);
              return;
            }
          } catch { /* listener is starting */ }
          await new Promise(wait => setTimeout(wait, 100));
        }
      }
    });
  });
}

try {
  const gateway = await start('ai-gateway', 'gateway');
  const jobs = await start('job-service', 'jobs', { FIXTURE_AI_GATEWAY_URL: gateway });
  const result = spawn(process.execPath, ['--test', 'tests/open-web-discovery.test.mjs'], {
    stdio: 'inherit', env: {
      ...process.env, CAREEROS_DISCOVERY_GATEWAY_URL: gateway, CAREEROS_DISCOVERY_JOB_URL: jobs,
      CAREEROS_DISCOVERY_GATEWAY_TOKEN: 'fixture-gateway', CAREEROS_DISCOVERY_JOB_TOKEN: 'fixture-discovery',
      CAREEROS_DISCOVERY_OWNER_TOKEN: 'fixture-owner', CAREEROS_DISCOVERY_OTHER_TOKEN: 'fixture-other',
    },
  });
  const [status] = await once(result, 'exit');
  process.exitCode = status ?? 1;
} finally {
  for (const server of servers) server.kill();
}
