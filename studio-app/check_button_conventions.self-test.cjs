/**
 * Self-test for the button-convention guard.
 *
 * The guard is a source heuristic, so its own detection is worth testing:
 * every rule below fails on the exact shape it exists to catch, and passes on
 * the shape it should accept. The last test scans the whole app source,
 * so this file is also a regression test for the real buttons.
 *
 * Run: npm run check:buttons:self-test
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const { scanSource } = require('./check_button_conventions.cjs');

const lines = (rows) => rows.map((row) => `${row.rel}:${row.line}`);

test('flags a button with no explicit type', () => {
  const result = scanSource('<button onClick={save}>Save</button>', 'fixture.tsx');
  assert.deepEqual(lines(result.missingType), ['fixture.tsx:1']);
});

test('accepts a typed synchronous button', () => {
  const result = scanSource('<button type="button" onClick={save}>Save</button>', 'fixture.tsx');
  assert.equal(result.missingType.length, 0);
  assert.equal(result.missingBusy.length, 0);
});

test('flags an inline async button with no in-flight state', () => {
  const result = scanSource(
    '<button type="submit" onClick={async () => { await save() }}>Save</button>',
    'fixture.tsx',
  );
  assert.equal(result.asyncButtons, 1);
  assert.match(result.missingBusy[0].missing, /aria-busy/);
  assert.match(result.missingBusy[0].missing, /disabled/);
});

test('flags the void promise() convention with no in-flight state', () => {
  const result = scanSource(
    '<button type="button" onClick={() => void save()}>Save</button>',
    'fixture.tsx',
  );
  assert.equal(result.asyncButtons, 1);
  assert.equal(result.missingBusy.length, 1);
});

test('requires re-entry protection even when aria-busy is present', () => {
  const result = scanSource(
    '<button type="button" onClick={() => void save()} aria-busy={saving || undefined}>Save</button>',
    'fixture.tsx',
  );
  assert.equal(result.missingBusy.length, 1);
  assert.equal(result.missingBusy[0].missing, 'disabled');
});

test('accepts aria-busy + disabled on an async button', () => {
  const result = scanSource(
    '<button type="button" onClick={() => void save()} disabled={saving} aria-busy={saving || undefined}>Save</button>',
    'fixture.tsx',
  );
  assert.equal(result.missingBusy.length, 0);
});

test('detects a handler declared async in the same file', () => {
  const source = [
    'const handleSave = async () => { await save() }',
    '<button type="button" onClick={handleSave}>Save</button>',
    '<button type="button" onClick={() => handleSave()}>Save again</button>',
  ].join('\n');
  const result = scanSource(source, 'fixture.tsx');
  assert.equal(result.asyncButtons, 2);
  assert.equal(result.missingBusy.length, 2);
});

test('detects an async handler followed by more attributes', () => {
  const source = [
    'const handleAssemble = useCallback(async () => { await assemble() }, [])',
    '<button type="button" onClick={handleAssemble} disabled={assembling} className={buttonClass}>Assemble</button>',
  ].join('\n');
  const result = scanSource(source, 'fixture.tsx');
  assert.equal(result.asyncButtons, 1);
  assert.equal(result.missingBusy.length, 1);
});

test('does not treat a synchronous handler as async', () => {
  const source = [
    'function handleToggle() { setOpen((open) => !open) }',
    '<button type="button" onClick={handleToggle}>Toggle</button>',
  ].join('\n');
  const result = scanSource(source, 'fixture.tsx');
  assert.equal(result.asyncButtons, 0);
  assert.equal(result.missingBusy.length, 0);
});

test('ignores the word button outside a JSX opening tag', () => {
  const source = [
    'const label = "button"',
    '// <button onClick={async () => { await save() }}>documented example</button>',
    '<button type="button" onClick={save}>Save</button>',
  ].join('\n');
  const result = scanSource(source, 'fixture.tsx');
  assert.equal(result.buttons, 1);
  assert.equal(result.missingType.length, 0);
  assert.equal(result.missingBusy.length, 0);
});

test('every async button in src exposes in-flight state', () => {
  const root = path.join(__dirname, 'src');
  const files = [];
  const walk = (dir) => {
    for (const name of fs.readdirSync(dir)) {
      const p = path.join(dir, name);
      if (fs.statSync(p).isDirectory()) walk(p);
      else if (p.endsWith('.tsx')) files.push(p);
    }
  };
  walk(root);
  for (const file of files) {
    const rel = path.relative(root, file).split(path.sep).join('/');
    const result = scanSource(fs.readFileSync(file, 'utf8'), rel);
    assert.deepEqual(lines(result.missingType), [], `${rel} has untyped buttons`);
    assert.deepEqual(
      result.missingBusy.map((row) => `${row.rel}:${row.line} → ${row.missing}`),
      [],
      `${rel} has async buttons without in-flight state`,
    );
  }
});
