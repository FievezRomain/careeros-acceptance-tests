import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const service = new URL('../../services/matching-service/', import.meta.url);
const python = process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python';
const scenarios = { extraction: 'matching-extraction.py', recommendations: 'recommendation-pipeline.py' };
const scenario = scenarios[process.argv[2]] ?? 'matching-baseline.py';
const test = fileURLToPath(new URL(`../tests/${scenario}`, import.meta.url));
const execution = spawnSync(fileURLToPath(new URL(python, service)), [test], { stdio: 'inherit' });
if (execution.error) throw execution.error;
process.exitCode = execution.status ?? 1;
