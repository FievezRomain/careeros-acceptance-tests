import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const service = new URL('../../services/resume-service/', import.meta.url);
const scenario = fileURLToPath(new URL('../tests/resume-versions.py', import.meta.url));
const result = spawnSync(fileURLToPath(new URL(python, service)), [scenario], { stdio: 'inherit' });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
