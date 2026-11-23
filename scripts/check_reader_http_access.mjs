#!/usr/bin/env node
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';

const args = process.argv.slice(2);
function option(name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : undefined;
}
const root = path.resolve(option('--bundle') || 'bundle');
const output = option('--output');
const checksums = JSON.parse(fs.readFileSync(path.join(root, 'checksums.json'), 'utf8'));
const expected = new Map(checksums.files.map(row => [row.path, row]));
const diskFiles = new Set();
function collectFiles(directory, prefix = '') {
  for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
    const relative = prefix ? `${prefix}/${entry.name}` : entry.name;
    const absolute = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Symlink is outside the static bundle contract: ${relative}`);
    if (entry.isDirectory()) collectFiles(absolute, relative);
    else if (entry.isFile()) diskFiles.add(relative);
    else throw new Error(`Unsupported bundle filesystem entry: ${relative}`);
  }
}
collectFiles(root);
const expectedDiskFiles = new Set([...expected.keys(), 'checksums.json']);
const unlistedDiskFiles = [...diskFiles].filter(file => !expectedDiskFiles.has(file));
const missingDiskFiles = [...expectedDiskFiles].filter(file => !diskFiles.has(file));
if (unlistedDiskFiles.length || missingDiskFiles.length) {
  throw new Error(`Bundle file/checksum inventory mismatch: unlisted=${unlistedDiskFiles.length}, missing=${missingDiskFiles.length}`);
}
const projection = JSON.parse(fs.readFileSync(path.join(root, 'okf-core-explorer.json'), 'utf8'));
const descriptor = JSON.parse(fs.readFileSync(path.join(root, 'okf-explorer.json'), 'utf8'));
const semanticManifest = JSON.parse(fs.readFileSync(path.join(root, 'data/semantic/manifest.json'), 'utf8'));
const routes = new Set([
  ...expected.keys(),
  'checksums.json',
  ...Object.keys(projection.nodes),
  'okf-core-explorer.json',
  'okf-explorer.json',
  'data/semantic/manifest.json',
  ...(semanticManifest.shards.entities || []).map(row => row.path),
  ...(semanticManifest.shards.assertions || []).map(row => row.path),
]);
if (Object.keys(projection.nodes).length !== 12 || projection.edges.length !== 0) {
  throw new Error('Core projection must contain 12 nodes and no concept graph edges');
}
if (!descriptor.entrypoints?.semantic_manifest || !semanticManifest.shards) {
  throw new Error('Large-corpus graph dependency manifest is incomplete');
}
for (const route of routes) {
  if (route !== 'checksums.json' && !expected.has(route)) {
    throw new Error(`Route is not covered by checksums.json: ${route}`);
  }
}

const server = http.createServer((request, response) => {
  const pathname = decodeURIComponent(new URL(request.url, 'http://localhost').pathname);
  const file = path.resolve(root, `.${pathname}`);
  if (!file.startsWith(`${root}${path.sep}`)) {
    response.writeHead(400).end();
    return;
  }
  fs.createReadStream(file)
    .on('error', () => response.writeHead(404).end())
    .pipe(response.writeHead(200, { 'content-type': 'application/octet-stream' }));
});

await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const { port } = server.address();
const retrieved = [];
const checksumManifestBytes = fs.readFileSync(path.join(root, 'checksums.json'));
const checksumManifestSha256 = crypto.createHash('sha256').update(checksumManifestBytes).digest('hex');
try {
  for (const route of [...routes].sort()) {
    const response = await fetch(`http://127.0.0.1:${port}/${route}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    const sha256 = crypto.createHash('sha256').update(bytes).digest('hex');
    const row = expected.get(route) || (route === 'checksums.json'
      ? { bytes: checksumManifestBytes.length, sha256: checksumManifestSha256 }
      : null);
    const passed = Boolean(row) && response.status === 200 && bytes.length === row.bytes && sha256 === row.sha256;
    retrieved.push({ path: route, status: response.status, bytes: bytes.length, sha256, passed });
    if (!passed) throw new Error(`HTTP digest check failed for ${route}`);
  }
} finally {
  await new Promise(resolve => server.close(resolve));
}
const receipt = {
  schema: 'okf-ons-reader-http-access.v1',
  bundle_root: root,
  method: 'loopback-http-get-body-sha256-v1',
  core_concepts: Object.keys(projection.nodes).length,
  core_concept_edges: projection.edges.length,
  extension_entity_count: descriptor.extensions['okf-core.v0.3'].reader_projection_scope.metadata_extension_entities,
  extension_relationship_count: descriptor.counts.relationships,
  graph_shard_count: (semanticManifest.shards.entities || []).length + (semanticManifest.shards.assertions || []).length,
  requested_files: retrieved.length,
  checksummed_bundle_files: expected.size,
  bundle_disk_files: diskFiles.size,
  complete_bundle_file_coverage: diskFiles.size === expectedDiskFiles.size &&
    [...diskFiles].every(file => expectedDiskFiles.has(file)),
  complete_checksums_file_coverage: expected.size === checksums.files.length &&
    checksums.files.every(row => retrieved.some(receipt => receipt.path === row.path && receipt.passed)),
  checksum_manifest_sha256: checksumManifestSha256,
  checksum_manifest_retrieved: retrieved.some(row => row.path === 'checksums.json' && row.passed),
  all_passed: retrieved.every(row => row.passed),
  files: retrieved,
};
if (output) {
  fs.mkdirSync(path.dirname(path.resolve(output)), { recursive: true, mode: 0o700 });
  fs.writeFileSync(output, `${JSON.stringify(receipt, null, 2)}\n`, { mode: 0o600 });
}
process.stdout.write(`HTTP retrieved and SHA-256 checked ${retrieved.length} core and graph files.\n`);
