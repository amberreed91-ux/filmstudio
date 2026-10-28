/**
 * Button-convention guard.
 *
 * Rules this enforces:
 *   1. Every <button> declares an explicit `type`. Buttons default to
 *      type="submit", so an untyped button inside a form submits it — a
 *      footgun that silently appears whenever someone wraps markup in a form.
 *   2. Every button that can start an asynchronous action reports its in-flight
 *      state: `aria-busy` for assistive technology, and `disabled` (or a
 *      pending flag wired into `disabled`) so the action cannot be re-entered.
 *
 * Both rules are fatal everywhere under src/. There is no backlog allowance:
 * an async button without in-flight state fails the build.
 *
 * Async detection is a source heuristic. A button counts as asynchronous when
 * its onClick is an async function, awaits, uses the `void promise()` intent
 * marker, or calls a handler declared async in the same file.
 *
 * Run:  npm run check:buttons
 * Test: npm run check:buttons:self-test
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, 'src');

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    if (fs.statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith('.tsx')) out.push(p);
  }
  return out;
}

/** Find the end of a JSX opening tag, skipping `>` inside strings and {…} expressions. */
function findTagEnd(text, from) {
  let quote = null;
  let depth = 0;
  for (let i = from; i < text.length; i++) {
    const ch = text[i];
    if (quote) {
      if (ch === '\\') { i++; continue; }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') { depth++; continue; }
    if (ch === '}') { depth--; continue; }
    if (ch === '>' && depth === 0) return i;
  }
  return -1;
}

/** Handler names declared async in the same file. */
function findAsyncHandlers(text) {
  const names = new Set();
  const patterns = [
    /\basync\s+function\s+([A-Za-z_$][\w$]*)/g,
    /\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]+)?=\s*async\b/g,
    /\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*useCallback\(\s*async\b/g,
  ];
  for (const pattern of patterns) {
    for (const match of text.matchAll(pattern)) names.add(match[1]);
  }
  return names;
}

/** Read a JSX attribute's `{…}` expression body with brace matching. */
function readBracedExpression(tag, attribute) {
  const match = new RegExp(`${attribute}\\s*=\\s*\\{`).exec(tag);
  if (!match) return null;
  const start = match.index + match[0].length;
  let depth = 0;
  let quote = null;
  for (let i = start - 1; i < tag.length; i++) {
    const ch = tag[i];
    if (quote) {
      if (ch === '\\') { i++; continue; }
      if (ch === quote) quote = null;
      continue;
    }
    if (ch === '"' || ch === "'" || ch === '`') { quote = ch; continue; }
    if (ch === '{') { depth++; continue; }
    if (ch === '}') {
      depth--;
      if (depth === 0) return tag.slice(start, i);
    }
  }
  return null;
}

/**
 * Heuristic: can this button start an asynchronous action?
 * Deliberately conservative — a false positive costs one `aria-busy`, while a
 * false negative is exactly the silent, re-enterable action this guard exists
 * to prevent.
 */
function isAsyncButton(tag, asyncHandlers) {
  const expression = readBracedExpression(tag, 'onClick');
  if (expression === null) return false;

  if (/^\s*async\b/.test(expression)) return true;
  if (/\bawait\b/.test(expression)) return true;
  // `void action()` is this codebase's marker for a fire-and-forget promise.
  if (/\bvoid\s+[A-Za-z_$]/.test(expression)) return true;

  const trimmed = expression.trim();
  for (const name of asyncHandlers) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    // Either a direct reference (`onClick={handleSave}`) or a call.
    if (trimmed === name || new RegExp(`\\b${escaped}\\s*\\(`).test(trimmed)) return true;
  }
  return false;
}

/** Skip markup that is commented out — documentation is not a rendered button. */
function isCommentedOut(text, idx) {
  const lineStart = text.lastIndexOf('\n', idx - 1) + 1;
  return /^\s*(?:\/\/|\*|\/\*|\{\/\*)/.test(text.slice(lineStart, idx));
}

/**
 * Scan one source file.
 * @returns {{ buttons: number, asyncButtons: number, missingType: number[], missingBusy: number[] }}
 */
function scanSource(text, rel = '<source>') {
  const asyncHandlers = findAsyncHandlers(text);
  const missingType = [];
  const missingBusy = [];
  let buttons = 0;
  let asyncButtons = 0;

  for (let cursor = 0; ; ) {
    const idx = text.indexOf('<button', cursor);
    if (idx === -1) break;
    if (isCommentedOut(text, idx)) { cursor = idx + 7; continue; }
    const after = text[idx + 7];
    if (!/[\s/>]/.test(after)) { cursor = idx + 7; continue; }
    const end = findTagEnd(text, idx + 7);
    if (end === -1) { cursor = idx + 7; continue; }

    const tag = text.slice(idx, end + 1);
    const line = text.slice(0, idx).split('\n').length;
    buttons += 1;

    if (!/\btype\s*=/.test(tag)) missingType.push({ rel, line });

    if (isAsyncButton(tag, asyncHandlers)) {
      asyncButtons += 1;
      const hasBusy = /aria-busy\s*=/.test(tag);
      const blocksReentry = /\bdisabled\s*=/.test(tag) || /\bloading\s*=/.test(tag);
      if (!hasBusy || !blocksReentry) {
        const missing = [
          !hasBusy ? 'aria-busy' : '',
          !blocksReentry ? 'disabled' : '',
        ].filter(Boolean).join(' + ');
        missingBusy.push({ rel, line, missing });
      }
    }

    cursor = end + 1;
  }

  return { buttons, asyncButtons, missingType, missingBusy };
}

function main() {
  const files = walk(SRC);
  const totals = { buttons: 0, asyncButtons: 0 };
  const failures = [];

  for (const file of files) {
    const rel = path.relative(SRC, file).split(path.sep).join('/');
    const result = scanSource(fs.readFileSync(file, 'utf8'), rel);
    totals.buttons += result.buttons;
    totals.asyncButtons += result.asyncButtons;
    for (const m of result.missingType) failures.push(`${m.rel}:${m.line} — no explicit type`);
    for (const m of result.missingBusy) failures.push(`${m.rel}:${m.line} — async action needs ${m.missing}`);
  }

  if (failures.length) {
    console.error(`Button check FAILED — ${failures.length} violation(s):`);
    for (const f of failures) console.error(`  ${f}`);
    console.error('\nAdd type="button" (or type="submit" for a form submit), and give async');
    console.error('buttons aria-busy + disabled — or use the <Button loading> primitive.');
    process.exit(1);
  }

  console.log(
    `Button check passed — ${totals.buttons} buttons declare a type; ` +
    `${totals.asyncButtons} async action(s) expose aria-busy and disable re-entry.`,
  );
}

module.exports = { scanSource };

if (require.main === module) main();
