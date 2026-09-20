import { copyFileSync, mkdirSync, readdirSync, writeFileSync, existsSync } from 'node:fs';
import { resolve, join } from 'node:path';

const disc = process.env.SOCOM_DISC ?? 'C:/projects/socom_pc/game/disc';
const web = resolve(import.meta.dirname, '..');
const run = join(disc, 'RUN');
if (!existsSync(run)) { console.error(`no disc tree at ${disc} (set SOCOM_DISC)`); process.exit(2); }

const mp = readdirSync(run).filter((f) => /^MP\d+\.ZDB$/.test(f)).sort();
const publicRun = join(web, 'public/maps/RUN');
const fixtureRun = join(web, 'test-fixtures/RUN');
mkdirSync(publicRun, { recursive: true });
mkdirSync(fixtureRun, { recursive: true });
for (const f of mp) copyFileSync(join(run, f), join(publicRun, f));
for (const f of ['MP2.ZDB', 'MP6.ZDB', 'MP72.ZDB']) copyFileSync(join(run, f), join(fixtureRun, f));
writeFileSync(join(web, 'public/maps/index.json'), JSON.stringify(mp.map((f) => `RUN/${f}`), null, 2));
console.log(`copied ${mp.length} archives to public/maps, 3 fixtures`);
