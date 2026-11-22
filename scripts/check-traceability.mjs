import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const defaultCatalog = resolve(root, '..', 'docs', 'business-rules', 'catalog.md');
const catalogPath = process.env.CAREEROS_RULES_CATALOG || defaultCatalog;
const requireFull = process.argv.includes('--require-full');

export function collectFeatureFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? collectFeatureFiles(path) : entry.name.endsWith('.feature') ? [path] : [];
  });
}

export function ruleIds(text) {
  return new Set(text.match(/BR-[A-Z]+-\d{3}/g) || []);
}

export function traceability(catalog, features) {
  const active = ruleIds(catalog);
  const referenced = new Set(features.flatMap((feature) => [...ruleIds(feature)]));
  return {
    active,
    referenced,
    unknown: [...referenced].filter((id) => !active.has(id)).sort(),
    missing: [...active].filter((id) => !referenced.has(id)).sort(),
  };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!existsSync(catalogPath)) {
    throw new Error(`Business-rule catalog not found: ${catalogPath}. Set CAREEROS_RULES_CATALOG for a standalone clone.`);
  }
  const files = collectFeatureFiles(join(root, 'features'));
  const report = traceability(readFileSync(catalogPath, 'utf8'), files.map((path) => readFileSync(path, 'utf8')));
  if (report.unknown.length) throw new Error(`Unknown business-rule tags: ${report.unknown.join(', ')}`);
  if (requireFull && report.missing.length) throw new Error(`Rules without acceptance scenarios: ${report.missing.join(', ')}`);
  console.log(`${report.referenced.size}/${report.active.size} active business rules referenced; ${report.missing.length} remain.`);
}
