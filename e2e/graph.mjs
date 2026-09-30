import { chromium } from 'playwright'
const b = await chromium.launch(); const p = await (await b.newContext({ viewport: { width: 1440, height: 1000 } })).newPage()
await p.goto('http://127.0.0.1:8000/login'); await p.waitForTimeout(800)
await p.locator('.demo-acc button').filter({ hasText: /^Admin/ }).click(); await p.waitForURL(/dashboard/)
for (const c of [1, 2]) { await p.goto(`http://127.0.0.1:8000/app/cases/${c}/relationships`); await p.waitForTimeout(4500); await p.locator('.graph-wrap').screenshot({ path: `e2e/shots/graph-${c}.png` }) }
await b.close()
