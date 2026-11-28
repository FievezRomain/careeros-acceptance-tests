import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const kind = process.argv[2];
if (kind !== 'extraction') throw new Error('Unknown ATS scenario');
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const executable = fileURLToPath(new URL(`../../services/ats-service/${python}`, import.meta.url));
const scenario = fileURLToPath(new URL('../tests/ats-extraction.py', import.meta.url));
const result = spawnSync(executable, [scenario], { stdio: 'inherit' });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
