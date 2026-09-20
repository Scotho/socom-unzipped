/** Throwaway: open the viewer and print whatever the page complains about. */
import { chromium } from '@playwright/test';

const browser = await chromium.launch();
const page = await browser.newPage();
page.on('pageerror', (e) => console.log('PAGEERROR:', e.message));
page.on('console', (m) => console.log(`console.${m.type()}:`, m.text()));
await page.goto(process.env.VIEWER_URL ?? 'http://localhost:5173/');
await page.waitForTimeout(6000);
console.log('status text:', await page.locator('#status').textContent());
await browser.close();
