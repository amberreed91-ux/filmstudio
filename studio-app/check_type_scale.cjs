/**
 * Type-scale guard.
 *
 * The studio's type scale (see src/index.css → `--type-*` tokens):
 *   10px  micro-label  uppercase + tracked labels, chips, telemetry codes
 *   11px  meta         captions, timestamps, secondary metadata
 *   12px  body         descriptions, advisories, button labels (= text-xs)
 *
 * RULE: never render a sentence below 12px. Sizes under 11px are reserved for
 * uppercase micro-labels and monospace telemetry codes — never prose.
 *
 * This check fails the build when a font size below the 10px hard floor comes
 * back, and reports (without failing) any reading text still under 12px.
 *
 * Run: npm run check:type-scale
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, 'src');
const HARD_FLOOR_PX = 10;
const READING_FLOOR_PX = 12;

// Intentional exceptions, with the reason each is allowed.
//   exempts: 'hard-floor'    — may render below 10px
//   exempts: 'reading-floor' — may render below 12px inside an internal tool,
//                              but still never below the 10px hard floor
const ALLOWLIST = [
  {
    file: 'components/Interactive3DLobby.tsx',
    exempts: 'hard-floor',
    reason: 'single letter inside a fixed 12x12 keycap box',
  },
  {
    file: 'pages/StudioDevTools.tsx',
    exempts: 'reading-floor',
    reason:
      'internal diagnostics console — dense monospace readouts and raw IDs for debugging, not creator-facing reading text',
  },
];

function walk(dir, out = []) {
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    if (fs.statSync(p).isDirectory()) walk(p, out);
    else if (p.endsWith('.tsx')) out.push(p);
  }
  return out;
}

// A line is "label-shaped" (small type is legitimate) when it carries an
// uppercase/tracked treatment, a monospace face, truncation, or a chip shape.
const LABEL_SIGNALS = /uppercase|font-mono|truncate|badge|chip|status|rounded-(full|md|lg|xl)\b/;

const hardFailures = [];
const readingWarnings = [];
const exceptions = [];

for (const file of walk(SRC)) {
  const rel = path.relative(SRC, file);
  const lines = fs.readFileSync(file, 'utf8').split('\n');

  lines.forEach((line, i) => {
    const m = line.match(/text-\[(\d+(?:\.\d+)?)px\]/);
    if (!m) return;
    const size = parseFloat(m[1]);
    const allowed = ALLOWLIST.find((a) => rel.endsWith(a.file));

    if (size < HARD_FLOOR_PX) {
      if (allowed?.exempts === 'hard-floor') {
        exceptions.push(`${rel}:${i + 1} [${size}px] allowed — ${allowed.reason}`);
        return;
      }
      hardFailures.push(`${rel}:${i + 1} [${size}px] below the ${HARD_FLOOR_PX}px hard floor`);
      return;
    }

    if (size >= READING_FLOOR_PX) return;
    if (LABEL_SIGNALS.test(line)) return;
    // Fixture markup is not product UI — report on it, but don't advise on it.
    const isTestFixture = rel.includes('.test.');

    // Reading text: the element renders words or bound content.
    let preview = '';
    const inline = line.match(/>([^<>{}]{10,})</);
    if (inline) preview = inline[1].trim();
    if (!preview) {
      for (let j = i; j < Math.min(i + 3, lines.length); j++) {
        const t = lines[j].match(/>([^<>{}]{10,})</);
        if (t) { preview = t[1].trim(); break; }
      }
    }
    if (/[a-z]\s+[a-z]/.test(preview) || /\{[a-zA-Z_.]/.test(line)) {
      if (isTestFixture) return;
      if (allowed) {
        exceptions.push(`${rel}:${i + 1} [${size}px] allowed — ${allowed.reason}`);
        return;
      }
      readingWarnings.push(`${rel}:${i + 1} [${size}px] reading text under ${READING_FLOOR_PX}px`);
    }
  });
}

if (exceptions.length) {
  console.log(`Type-scale allowlist — ${exceptions.length} documented exception(s):`);
  for (const e of exceptions) console.log(`  ${e}`);
  console.log('');
}

if (readingWarnings.length) {
  console.log(`Type-scale report — ${readingWarnings.length} site(s) to review:`);
  for (const w of readingWarnings) console.log(`  ${w}`);
  console.log('');
}

if (hardFailures.length) {
  console.error(`Type-scale check FAILED — ${hardFailures.length} violation(s):`);
  for (const f of hardFailures) console.error(`  ${f}`);
  console.error('\nUse text-[10px] or larger, or a named scale step (text-xs / text-sm / ...).');
  process.exit(1);
}

const outstanding = readingWarnings.length === 0
  ? 'no outstanding reading-text warnings'
  : `${readingWarnings.length} reading-text warning(s) outstanding`;
console.log(`Type-scale check passed (hard floor ${HARD_FLOOR_PX}px, ${outstanding}).`);
