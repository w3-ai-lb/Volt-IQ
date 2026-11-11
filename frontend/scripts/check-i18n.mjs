#!/usr/bin/env node
/**
 * Checks the interface catalogue against the code that uses it.
 *
 *     npm run check:i18n            (from the frontend folder)
 *     node scripts/check-i18n.mjs --dynamic   also lists t(<expression>) calls
 *
 * FAILS (exit code 1) WHEN
 *   - a t('...') call in src/ names a phrase the catalogue does not have, or has
 *     without one of the six translations;
 *   - a phrase and one of its translations do not use the same {placeholders},
 *     which would leave a "{name}" on the screen or drop a value;
 *   - a translation is empty, or Arabic has a phrase the other five do not.
 *
 * REPORTS, WITHOUT FAILING
 *   - catalogue phrases that no file in src/ mentions any more and that the
 *     backend does not send either. A phrase can reach t() from the API (a
 *     status such as "Pending", a refusal such as "Invalid credentials"), so the
 *     string literals of backend/app are read too, and a phrase found there
 *     counts as used. What is left is for a person to check, not for this
 *     script to delete.
 *
 * The catalogue files are TypeScript; they are compiled in memory with the
 * project's own TypeScript package, so nothing new is installed.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import ts from 'typescript';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = join(root, 'src');
const LANGS = ['es', 'fr', 'de', 'zh', 'ja'];

function load(file, imports = {}) {
  const code = ts.transpileModule(readFileSync(join(src, file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const module = { exports: {} };
  vm.runInNewContext(code, { module, exports: module.exports, require: (name) => imports[name] });
  return module.exports;
}

// translations.ts keeps its rows in an unexported constant; read them from the
// merged export instead, which is what t() itself uses.
const { ARABIC } = load('i18n/arabic.ts');
const { TRANSLATIONS } = load('i18n/translations.ts', { '@/i18n/arabic': { ARABIC } });

// Passed through t() but the same in every language by design, so they have no
// entry (see the note at the top of src/i18n/translations.ts): the brand, the
// unit, file formats and a sample address in a placeholder.
const INVARIANT = new Set(['VoltIQ', 'kWh', 'PDF', 'Excel', 'you@example.com']);

const placeholders = (text) => [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(',');
const problems = [];

const english = new Set(Object.keys(TRANSLATIONS.es ?? {}));
for (const key of english) {
  for (const lang of [...LANGS, 'ar']) {
    const value = TRANSLATIONS[lang]?.[key];
    if (value === undefined) problems.push(`no ${lang} translation: ${JSON.stringify(key)}`);
    else if (!value.trim()) problems.push(`empty ${lang} translation: ${JSON.stringify(key)}`);
    else if (placeholders(value) !== placeholders(key)) {
      problems.push(`${lang} placeholders differ: ${JSON.stringify(key)} -> ${JSON.stringify(value)}`);
    }
  }
}
for (const key of Object.keys(ARABIC)) {
  if (!english.has(key)) problems.push(`Arabic only, missing from the other five: ${JSON.stringify(key)}`);
}

function* sourceFiles(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      if (path !== join(src, 'i18n')) yield* sourceFiles(path);
    } else if (/\.(ts|tsx)$/.test(name)) {
      yield path;
    }
  }
}

const used = new Set();
const literals = new Set();
const dynamic = [];
for (const file of sourceFiles(src)) {
  const text = readFileSync(file, 'utf8');
  const tree = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true,
    file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const where = (node) => `${relative(root, file)}:${tree.getLineAndCharacterOfPosition(node.getStart()).line + 1}`;
  const visit = (node) => {
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) literals.add(node.text);
    // t(phrase), and errorMessage(error, fallback), whose fallback goes through t().
    const callee = ts.isCallExpression(node) && ts.isIdentifier(node.expression) ? node.expression.text : null;
    if (callee === 't' || (callee === 'errorMessage' && node.arguments.length > 1)) {
      const arg = node.arguments[callee === 't' ? 0 : 1];
      if (arg && (ts.isStringLiteral(arg) || ts.isNoSubstitutionTemplateLiteral(arg))) {
        used.add(arg.text);
        if (!english.has(arg.text) && !INVARIANT.has(arg.text)) problems.push(`${where(node)} not in the catalogue: ${JSON.stringify(arg.text)}`);
      } else if (arg) {
        dynamic.push(`${where(node)} t(${arg.getText(tree)})`);
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(tree);
}

// The backend's own string literals: statuses, enumerations and refusals that
// arrive from the API and are passed to t() by the pages.
const backend = new Set();
function* pythonFiles(dir) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) yield* pythonFiles(path);
    else if (name.endsWith('.py')) yield path;
  }
}
const backendApp = join(root, '..', 'backend', 'app');
try {
  for (const file of pythonFiles(backendApp)) {
    // Adjacent literals are one string in Python ("abc " "def"), as a long
    // message split over several lines is written; each run is joined.
    const literal = /"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'/g;
    const run = /(?:"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')(?:\s*(?:"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'))*/g;
    for (const r of readFileSync(file, 'utf8').matchAll(run)) {
      const parts = [...r[0].matchAll(literal)].map((m) => (m[1] ?? m[2]).replace(/\\(["'\\])/g, '$1'));
      parts.forEach((part) => backend.add(part));
      backend.add(parts.join(''));
    }
  }
} catch {
  // Only the frontend checked out: every API phrase is then reported below.
}

const unused = [...english].filter((key) => !literals.has(key) && !backend.has(key)).sort();
console.log(`catalogue: ${english.size} phrases; t() with a literal: ${used.size} distinct phrases`);
if (process.argv.includes('--dynamic')) {
  console.log(`\nt() with an expression (${dynamic.length}), each to be checked by hand:`);
  dynamic.forEach((line) => console.log(`  ${line}`));
}
console.log(`\nnot used in src/ and not sent by the backend (${unused.length}): obsolete, or used in a way this script cannot see`);
unused.forEach((key) => console.log(`  ${JSON.stringify(key)}`));
if (problems.length) {
  console.error(`\n${problems.length} problem(s):`);
  problems.forEach((p) => console.error(`  ${p}`));
  process.exit(1);
}
console.log('\nno problems');
