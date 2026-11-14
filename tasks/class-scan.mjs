/**
 * The used-vs-defined CSS class scan used by T25 and T26.
 *
 * Node built-ins only — no dependency, nothing installed, nothing fetched.
 * Run it from the repository root:
 *
 *     node tasks/class-scan.mjs frontend/src
 *
 * It prints one line per direction and exits non-zero when either direction
 * is not empty, so it can be used as a gate:
 *
 *     defined-but-unused: (none)
 *     used-but-undefined: (none)
 *
 * "Defined" is every class selector written in `src/styles/*.css`.
 * "Used" is every class token that appears in a `className` attribute in
 * `src/**\/*.{ts,tsx}` — the tokens inside a ternary's condition (`cond ? "a"`)
 * are skipped, because a condition operand is not a class.
 */

import fs from "node:fs";
import path from "node:path";

const root = process.argv[2] ?? "frontend/src";

/** Every file under `dir`, recursively. */
function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}

const files = walk(root);
const cssFiles = files.filter((file) => file.endsWith(".css"));
const codeFiles = files.filter(
  (file) => /\.(tsx|ts)$/.test(file) && !file.split(path.sep).includes("styles"),
);

const defined = new Set();
for (const file of cssFiles) {
  const text = fs.readFileSync(file, "utf8");
  for (const match of text.matchAll(/(?<![\w-])\.([a-zA-Z][\w-]*)/g)) {
    defined.add(match[1]);
  }
}

const used = new Set();
for (const file of codeFiles) {
  const text = fs.readFileSync(file, "utf8");
  const attributes = text.matchAll(/className\s*=\s*(\{[^}]*\}|"[^"]*")/g);
  for (const attribute of attributes) {
    const expression = attribute[1];
    for (const literal of expression.matchAll(/"([^"\n]*)"/g)) {
      const after = expression.slice(literal.index + literal[0].length);
      // A ternary's condition operand is not a class name.
      if (/^\s*\?/.test(after)) {
        continue;
      }
      for (const token of literal[1].split(/\s+/)) {
        const name = token.replace(/\$\{[^}]*\}/g, "").trim();
        if (/^[a-zA-Z][\w-]*$/.test(name)) {
          used.add(name);
        }
      }
    }
  }
}

const unused = [...defined].filter((name) => !used.has(name)).sort();
const undefinedClasses = [...used].filter((name) => !defined.has(name)).sort();

console.log("defined-but-unused:", unused.length ? unused.join(", ") : "(none)");
console.log(
  "used-but-undefined:",
  undefinedClasses.length ? undefinedClasses.join(", ") : "(none)",
);

process.exitCode = unused.length === 0 && undefinedClasses.length === 0 ? 0 : 1;
