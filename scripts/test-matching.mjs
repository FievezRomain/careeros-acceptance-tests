import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const service = new URL('../../services/matching-service/', import.meta.url);
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const test = fileURLToPath(new URL('../tests/matching-baseline.py', import.meta.url));
const execution = spawnSync(fileURLToPath(new URL(python, service)), [test], { stdio: 'inherit' });
if (execution.error) throw execution.error;
process.exitCode = execution.status ?? 1;
