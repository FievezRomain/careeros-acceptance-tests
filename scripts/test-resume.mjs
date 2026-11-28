import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const service = new URL('../../services/resume-service/', import.meta.url);
const kind = process.argv[2];
if (kind !== 'versions' && kind !== 'drafts') throw new Error('Unknown resume scenario');
const scenario = fileURLToPath(new URL(`../tests/resume-${kind}.py`, import.meta.url));
const result = spawnSync(fileURLToPath(new URL(python, service)), [scenario], { stdio: 'inherit' });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
