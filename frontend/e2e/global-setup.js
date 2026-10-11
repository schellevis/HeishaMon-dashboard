import fs from 'node:fs';
import { PYTHON, DIST } from './stack.js';

export default async function globalSetup() {
  if (!fs.existsSync(PYTHON)) throw new Error(`missing ${PYTHON}`);
  if (!fs.existsSync(`${DIST}/index.html`)) throw new Error(`no build at ${DIST}; run npm run build first`);
}
