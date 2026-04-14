/* global console */
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const packageRoot = join(here, '..');
const distEsm = join(packageRoot, 'dist/index.js');
const distCjs = join(packageRoot, 'dist/index.cjs');
const require = createRequire(import.meta.url);

await import(pathToFileURL(distEsm).href);
require(distCjs);

console.log('Verified dist ESM and CJS entrypoints.');
