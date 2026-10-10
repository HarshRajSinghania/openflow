import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
test('Nano Banana 2 routes to live Nano Banana 2.1 BELUGA',()=>{ const source=fs.readFileSync(new URL('../operations.mjs',import.meta.url),'utf8'); assert.match(source,/nano_banana_2: "BELUGA"/); });
