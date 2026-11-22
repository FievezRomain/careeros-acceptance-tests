import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import test from 'node:test';
import { baselineDelta, collectFeatureFiles, ruleIds, traceability } from '../scripts/check-traceability.mjs';

test('rule identifiers have a stable format', () => {
  assert.deepEqual([...ruleIds('x BR-ACC-001 y BR-RES-010')], ['BR-ACC-001', 'BR-RES-010']);
});

test('traceability rejects unknown rule tags', () => {
  const report = traceability('| BR-ACC-001 | Rule |', ['@BR-ACC-001 @BR-NOPE-999']);
  assert.deepEqual(report.unknown, ['BR-NOPE-999']);
  assert.deepEqual(report.missing, []);
});

test('baseline allows existing gaps but rejects a new uncovered rule', () => {
  const report = traceability('| BR-ACC-001 | A |\n| BR-ACC-002 | B |', ['@BR-ACC-001']);
  assert.deepEqual(baselineDelta(report, ['BR-ACC-002']), { newGaps: [], staleEntries: [] });
  assert.deepEqual(baselineDelta(report, []), { newGaps: ['BR-ACC-002'], staleEntries: [] });
});

test('baseline must shrink when a rule becomes covered', () => {
  const report = traceability('| BR-ACC-001 | A |', ['@BR-ACC-001']);
  assert.deepEqual(baselineDelta(report, ['BR-ACC-001']), { newGaps: [], staleEntries: ['BR-ACC-001'] });
});

test('repository scenarios reference only catalog rules', () => {
  const catalogPath = process.env.CAREEROS_RULES_CATALOG || resolve('..', 'docs', 'business-rules', 'catalog.md');
  const features = collectFeatureFiles(resolve('features')).map((path) => readFileSync(path, 'utf8'));
  const report = traceability(readFileSync(catalogPath, 'utf8'), features);
  assert.deepEqual(report.unknown, []);
  assert.ok(report.referenced.size > 0);
});
