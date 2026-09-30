import { chromium } from 'playwright'
const b = await chromium.launch(); const ctx = await b.newContext({ viewport: { width: 390, height: 844 } }); const p = await ctx.newPage()
await p.goto('http://127.0.0.1:8000/login'); await p.waitForTimeout(800)
await p.locator('.demo-acc button').filter({ hasText: /^Admin/ }).click(); await p.waitForURL(/dashboard/)
for (const path of ['records']) {
  await p.goto('http://127.0.0.1:8000/app/' + path); await p.waitForTimeout(2000)
  const r = await p.evaluate(() => [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > window.innerWidth + 1 && !e.closest('.sidebar') && !e.closest('.bg-layer')).slice(0, 6).map(e => e.tagName + '.' + e.className.toString().slice(0, 50) + ' ' + Math.round(e.getBoundingClientRect().right)))
  console.log(path, r)
}
await b.close()
