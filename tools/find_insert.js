const fs = require('fs');
const path = require('path');

function slugify(input) {
  let s = input.trim().toLowerCase();
  s = s.normalize('NFKD').replace(/\p{M}/gu, '');
  s = s.replace(/[^a-z0-9]+/g, '-');
  s = s.replace(/-+/g, '-');
  s = s.replace(/^-|-$|^$/g, '');
  return s;
}

function generateSnippet(slug, pretty) {
  return `  "${slug}": {
    "aliases": ["${slug}"],
    "categories": ["stimulant"],
    "name": "${slug}",
    "pretty_name": "${pretty}",
    "properties": {
      "summary": "Add a short summary here."
    }
  },`;
}

function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    console.error('Usage: node tools/find_insert.js <Drug Name> [drugs.json]');
    process.exit(1);
  }
  const drug = args[0];
  const jsonPath = args[1] || 'drugs.json';
  if (!fs.existsSync(jsonPath)) {
    console.error('drugs.json not found at ' + path.resolve(jsonPath));
    process.exit(2);
  }
  const lines = fs.readFileSync(jsonPath, 'utf8').split(/\r?\n/);
  const keys = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const m = line.match(/^\s*"([^"]+)"\s*:\s*\{/);
    if (m) keys.push({ key: m[1], line: i + 1 });
  }
  if (!keys.length) {
    console.error('No top-level keys found');
    process.exit(3);
  }
  keys.sort((a,b)=> a.key.localeCompare(b.key));
  const slug = slugify(drug);
  const found = keys.find(k => k.key === slug);
  if (found) {
    console.log(`Found existing key '${found.key}' at line ${found.line}`);
    return;
  }
  let insertIndex = 0;
  while (insertIndex < keys.length && keys[insertIndex].key < slug) insertIndex++;
  const prev = insertIndex - 1 >= 0 ? keys[insertIndex - 1] : null;
  const next = insertIndex < keys.length ? keys[insertIndex] : null;
  console.log(`Suggested slug: '${slug}' (from '${drug}')`);
  if (prev) console.log(`Insert after: '${prev.key}' (line ${prev.line})`);
  else if (next) console.log(`Insert at start (before: '${next.key}' line ${next.line})`);
  if (next) console.log(`Insert before: '${next.key}' (line ${next.line})`);
  else if (prev) console.log(`Insert at end (after: '${prev.key}' line ${prev.line})`);
  console.log('\nSuggested JSON snippet:');
  console.log('\n' + generateSnippet(slug, drug));
}

main();
