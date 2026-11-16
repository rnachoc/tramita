// Copies the policy clauses (the file the rules cite) into the console's public assets, keeping
// only what the console shows. Runs before every build, serve and test.
import { readFileSync, writeFileSync } from 'node:fs';

const source = new URL('../../../data/policies/clauses.json', import.meta.url);
const target = new URL('../public/clauses.json', import.meta.url);
const clauses = JSON.parse(readFileSync(source, 'utf8')).map(
  ({ clause_id, product_code, title, text }) => ({ clause_id, product_code, title, text }),
);
writeFileSync(target, JSON.stringify(clauses));
console.log(`copied ${clauses.length} clauses`);
