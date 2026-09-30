// Browser walkthrough: node e2e/walkthrough.mjs [baseUrl]  — screenshots in e2e/shots, fails on console errors.
import { chromium } from 'playwright'
import fs from 'fs'

const BASE = process.argv[2] || 'http://127.0.0.1:8000'
const OUT = new URL('./shots/', import.meta.url).pathname
fs.mkdirSync(OUT, { recursive: true })
const errors = []
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const browser = await chromium.launch({ executablePath: fs.existsSync('/opt/pw-browsers/chromium') ? undefined : undefined })
async function newPage(viewport = { width: 1440, height: 900 }, scheme = 'dark') {
  const ctx = await browser.newContext({ viewport, colorScheme: scheme })
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`[console] ${page.url()} :: ${m.text()}`) })
  page.on('pageerror', (e) => errors.push(`[pageerror] ${page.url()} :: ${e.message}`))
  page.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 500) errors.push(`[5xx] ${r.status()} ${r.url()}`) })
  return page
}
const shot = (page, name, full = false) => page.screenshot({ path: `${OUT}${name}.png`, fullPage: full })

// ---------------- admin demo flow
let page = await newPage()
await page.goto(BASE + '/')
await sleep(1500)
await shot(page, '01-landing')
await page.getByRole('button', { name: 'Launch Demo' }).first().click()
await page.waitForSelector('.pipeline', { timeout: 15000 })
await sleep(2200)
await shot(page, '02-pipeline-running')
await page.getByRole('button', { name: 'Explore results' }).waitFor({ timeout: 40000 })
await sleep(600)
await shot(page, '03-pipeline-complete')
await page.getByRole('button', { name: 'Explore results' }).click()
await sleep(1200)
await shot(page, '04-case-overview')

const caseUrl = page.url().split('?')[0]
for (const tab of ['records', 'timeline', 'relationships', 'conflicts', 'review', 'reports', 'audit']) {
  await page.goto(`${caseUrl}/${tab}`)
  await sleep(tab === 'relationships' ? 4500 : tab === 'timeline' ? 2600 : 1400)
  await shot(page, `05-case-${tab}`)
}
// graph interaction: click a person node
const person = page.locator('.gnode').filter({ hasText: 'Rahul Kumaar' }).first()
await page.goto(`${caseUrl}/relationships`); await sleep(4500)
if (await person.count()) { await person.click(); await sleep(600); await shot(page, '06-graph-selected') }

// review a conflict
await page.goto(`${caseUrl}/conflicts`); await sleep(1200)
await page.getByRole('button', { name: 'Resolve' }).first().click()
await sleep(500)
await page.fill('#rv-note', 'Supporting document confirmed the later date.')
await shot(page, '07-review-dialog')
await page.locator('.modal-foot .btn.primary').click()
await sleep(1500)
await shot(page, '08-after-review')

// report generation
await page.goto(`${caseUrl}/reports`); await sleep(1000)
await page.getByRole('button', { name: 'Generate report' }).click()
await page.getByRole('button', { name: 'Assemble report' }).click()
await sleep(1200)
await shot(page, '09-report-assembling')
await page.getByRole('button', { name: 'Download PDF' }).waitFor({ timeout: 15000 })
await sleep(400)
await shot(page, '10-report-done')
await page.keyboard.press('Escape')
await sleep(600)
await page.getByRole('button', { name: 'Preview' }).first().click(); await sleep(1800)
await shot(page, '11-report-preview')
await page.keyboard.press('Escape')

// record detail
await page.goto(`${caseUrl}/records`); await sleep(1000)
const rec = await page.locator('a[href^="/app/records/"]').first().getAttribute('href')
for (const [i, rid] of [[1, 3], [2, 4]]) {
  await page.goto(`${BASE}/app/records/${rid}`); await sleep(2000)
  await shot(page, `12-record-${i}`)
  await page.goto(`${BASE}/app/records/${rid}#extracted`); await sleep(1800)
  await shot(page, `12-record-${i}-extracted`)
}

for (const p of ['dashboard', 'cases', 'records', 'timeline', 'graph', 'conflicts', 'review', 'reports', 'audit', 'users', 'settings', 'search?q=Kumaar']) {
  await page.goto(`${BASE}/app/${p}`)
  await sleep(p === 'graph' ? 4000 : 1800)
  await shot(page, `20-${p.split('?')[0]}`)
}
// global search dropdown + notifications
await page.goto(`${BASE}/app/dashboard`); await sleep(1500)
await page.fill('input[aria-label="Global search"]', 'WGU22')
await sleep(900); await shot(page, '21-search-dropdown')
await page.keyboard.press('Escape')
await page.getByRole('button', { name: /Notifications/ }).click(); await sleep(600); await shot(page, '22-notifications')

// upload a new case
await page.goto(`${BASE}/app/cases`); await sleep(800)
await page.getByRole('button', { name: 'Create case' }).first().click()
await page.fill('#cn', 'Browser upload test')
await page.locator('.modal-foot .btn.primary').click()
await page.waitForURL(/records$/, { timeout: 8000 }); await sleep(800)
const fileInput = page.locator('input[type=file]')
await fileInput.setInputFiles(['/home/claude/drcv/backend/demo_files/11_Invoice_INV-2026-1142.pdf', '/home/claude/drcv/backend/demo_files/14_Payment_Record_TXN88213490.jpg'])
await sleep(1500); await shot(page, '23-upload-progress')
await page.waitForSelector('.upload-item .btn.warn, .upload-item a.btn.ghost', { timeout: 30000 }); await sleep(3500)
await shot(page, '24-upload-done')

// light theme
await page.goto(`${BASE}/app/dashboard`); await sleep(800)
await page.getByRole('button', { name: /Switch to light theme/ }).click(); await sleep(1500)
await shot(page, '25-dashboard-light')
await page.goto(`${caseUrl}/timeline`); await sleep(2500); await shot(page, '26-timeline-light')
await page.getByRole('button', { name: /Switch to dark theme/ }).click()

// ---------------- viewer (RBAC in UI)
page = await newPage()
await page.goto(BASE + '/login'); await sleep(1500)
await shot(page, '30-login')
await page.locator('.demo-acc button').filter({ hasText: /^Viewer/ }).click()
await page.waitForURL(/dashboard/); await sleep(1500)
await shot(page, '31-viewer-dashboard')
await page.goto(`${caseUrl}/records`); await sleep(1500)
const hasUpload = await page.locator('.dropzone').count()
if (hasUpload) errors.push('[rbac] viewer sees upload zone')
await page.goto(`${caseUrl}/conflicts`); await sleep(1200)
if (await page.getByRole('button', { name: 'Resolve' }).count()) errors.push('[rbac] viewer sees Resolve')
await shot(page, '32-viewer-conflicts')
await page.goto(`${BASE}/app/users`); await sleep(1000); await shot(page, '33-viewer-users-denied')
if (await page.locator('a[href="/app/users"]').count()) errors.push('[rbac] viewer sees users nav')

// ---------------- mobile
page = await newPage({ width: 390, height: 844 })
await page.goto(BASE + '/'); await sleep(1500); await shot(page, '40-mobile-landing', true)
await page.goto(BASE + '/login'); await sleep(800)
await page.locator('.demo-acc button').filter({ hasText: /^Reviewer/ }).click()
await page.waitForURL(/dashboard/); await sleep(1800)
await shot(page, '41-mobile-dashboard', true)
await page.getByRole('button', { name: 'Open navigation' }).click(); await sleep(600); await shot(page, '42-mobile-nav')
await page.goto(`${caseUrl}/timeline`); await sleep(2500); await shot(page, '43-mobile-timeline')
await page.goto(`${caseUrl}/conflicts`); await sleep(1500); await shot(page, '44-mobile-conflicts')
await page.goto(`${caseUrl}/relationships`); await sleep(4000); await shot(page, '45-mobile-graph')
const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)
if (overflow) errors.push('[layout] horizontal overflow on mobile graph page')
for (const p of ['dashboard', 'records', 'review', 'settings']) {
  await page.goto(`${BASE}/app/${p}`); await sleep(1200)
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)) errors.push(`[layout] horizontal overflow on mobile ${p}`)
}

await browser.close()
console.log(errors.length ? `ERRORS (${errors.length}):\n` + errors.join('\n') : 'NO CONSOLE / PAGE / 5xx ERRORS')
