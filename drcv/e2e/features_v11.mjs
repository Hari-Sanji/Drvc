// Browser checks for v1.1 features: node e2e/features_v11.mjs [baseUrl]
import { chromium } from 'playwright'
import crypto from 'crypto'
import fs from 'fs'

const BASE = process.argv[2] || 'http://127.0.0.1:8000'
const OUT = new URL('./shots/', import.meta.url).pathname
const DEMO = new URL('../backend/demo_files/', import.meta.url).pathname
fs.mkdirSync(OUT, { recursive: true })
const errors = []
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const check = (cond, msg) => { if (!cond) errors.push('[check] ' + msg); else console.log('  ✓', msg) }

function totp(secret) {
  const alph = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'
  let bits = ''
  for (const ch of secret.replace(/=+$/, '')) bits += alph.indexOf(ch).toString(2).padStart(5, '0')
  const key = Buffer.from(bits.match(/.{8}/g).map((b) => parseInt(b, 2)))
  const buf = Buffer.alloc(8); buf.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 1000 / 30)))
  const h = crypto.createHmac('sha1', key).update(buf).digest()
  const o = h[h.length - 1] & 15
  return String(((h.readUInt32BE(o) & 0x7fffffff) % 1000000)).padStart(6, '0')
}

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true })
const page = await ctx.newPage()
page.on('console', (m) => { if (m.type() === 'error') errors.push(`[console] ${page.url()} :: ${m.text()}`) })
page.on('pageerror', (e) => errors.push(`[pageerror] ${page.url()} :: ${e.message}`))
page.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 500) errors.push(`[5xx] ${r.status()} ${r.url()}`) })

// #41 try-it without login
await page.goto(BASE + '/'); await sleep(1200)
await page.locator('.try-zone input[type=file]').setInputFiles(DEMO + '14_Payment_Record_TXN88213490.jpg')
await page.waitForSelector('.try-result', { timeout: 40000 }); await sleep(600)
await page.locator('.try-zone').scrollIntoViewIfNeeded()
await page.locator('.try-zone').screenshot({ path: OUT + 'v11-try-it.png' })
check(await page.locator('.try-result').getByText('Editing software recorded in metadata').count() > 0, 'try-it shows metadata signal')
check(await page.locator('.try-result .hash').count() === 1, 'try-it shows SHA-256')

// login as admin
await page.goto(BASE + '/login'); await sleep(800)
await page.locator('.demo-acc button').filter({ hasText: /^Admin/ }).click(); await page.waitForURL(/dashboard/); await sleep(800)

// #9 why flagged + #21 bulk
await page.goto(BASE + '/app/conflicts'); await sleep(1500)
await page.locator('.why summary').first().click(); await sleep(400)
await page.locator('.conflict').first().screenshot({ path: OUT + 'v11-why-flagged.png' })
check(await page.locator('.why[open] .quote mark').count() > 0, 'evidence quote highlights the value')
const boxes = page.locator('.bulk-check')
const nBox = await boxes.count()
check(nBox >= 3, `bulk checkboxes shown (${nBox})`)
await boxes.nth(0).check(); await boxes.nth(1).check(); await sleep(300)
check(await page.locator('.bulk-bar').getByText('2 selected').count() === 1, 'bulk bar shows selection')
await page.locator('.bulk-bar select').selectOption('accept')
await page.locator('.bulk-bar input').fill('Confirmed with the issuing office by phone')
await page.screenshot({ path: OUT + 'v11-bulk-bar.png' })
await page.locator('.bulk-bar').getByRole('button', { name: /Apply to 2/ }).click(); await sleep(1500)
check(await page.locator('.toast').filter({ hasText: /2 items/ }).count() > 0, 'bulk action applied to 2 items')

// #8 merged timeline
await page.goto(BASE + '/app/cases/1/timeline'); await sleep(2500)
check(await page.getByText('Stated in 4 records').count() > 0, 'timeline merges date of birth into one event (4 records)')
await page.locator('.tl-item').first().screenshot({ path: OUT + 'v11-timeline-merged.png' })

// #3 #4 record detail
await page.goto(BASE + '/app/records/1#integrity'); await sleep(2000)
check(await page.getByText('Signed bytes intact').count() > 0, 'signature shown intact on semester marksheet')
await page.locator('#integrity').screenshot({ path: OUT + 'v11-signature.png' })
await page.goto(BASE + '/app/records/3#metadata'); await sleep(2000)
check(await page.locator('.flag-row').filter({ hasText: 'Modified date is earlier than created date' }).count() > 0, 'metadata signal shown on degree certificate')
await page.locator('#metadata').screenshot({ path: OUT + 'v11-metadata-flag.png' })

// #16 PDF downloads
await page.goto(BASE + '/app/cases/1/reports'); await sleep(1000)
await page.getByRole('button', { name: 'Generate report' }).click()
await page.getByRole('button', { name: 'Assemble report' }).click()
await page.getByRole('button', { name: 'Download PDF' }).waitFor({ timeout: 15000 }); await sleep(300)
await page.screenshot({ path: OUT + 'v11-report-buttons.png' })
const [dl] = await Promise.all([page.waitForEvent('download'), page.locator('.modal-foot').getByRole('button', { name: 'Download PDF' }).click()])
const p1 = await dl.path(); check(fs.readFileSync(p1).subarray(0, 4).toString() === '%PDF', `PDF downloaded (${dl.suggestedFilename()})`)
const [dl2] = await Promise.all([page.waitForEvent('download'), page.locator('.modal-foot').getByRole('button', { name: 'Summary PDF' }).click()])
check(fs.readFileSync(await dl2.path()).subarray(0, 4).toString() === '%PDF', `summary PDF downloaded (${dl2.suggestedFilename()})`)
await page.keyboard.press('Escape')

// #28 audit verify
await page.goto(BASE + '/app/audit'); await sleep(1200)
await page.getByRole('button', { name: 'Verify integrity' }).click(); await sleep(1500)
check(await page.locator('.chain-ok').count() === 1, 'audit chain verifies in the UI')
await page.screenshot({ path: OUT + 'v11-audit-chain.png' })

// #24 create a user, set up 2FA, sign in with code
await page.goto(BASE + '/app/users'); await sleep(1000)
await page.getByRole('button', { name: 'Create user' }).first().click()
await page.fill('#un', 'Test Analyst'); await page.fill('#ue', 'analyst@example.org'); await page.selectOption('#ur', 'investigator'); await page.fill('#up', 'Analyst2026')
await page.locator('.modal-foot .btn.primary').click(); await sleep(1000)
await page.getByRole('button', { name: 'Sign out' }).click(); await sleep(800)
await page.goto(BASE + '/login'); await sleep(600)
await page.fill('#email', 'analyst@example.org'); await page.fill('#password', 'Analyst2026'); await page.getByRole('button', { name: 'Sign in', exact: true }).click()
await page.waitForURL(/dashboard/); await sleep(800)
await page.goto(BASE + '/app/settings'); await sleep(1200)
await page.getByRole('button', { name: 'Set up two-factor authentication' }).click(); await sleep(800)
check(await page.locator('.qr-box svg').count() === 1, '2FA QR code rendered')
await page.locator('.card').filter({ hasText: 'Security' }).first().screenshot({ path: OUT + 'v11-2fa-setup.png' })
const secret = (await page.locator('code.mono').first().innerText()).replace(/\s/g, '')
await page.fill('input[aria-label="Authenticator code"]', totp(secret))
await page.getByRole('button', { name: 'Turn on' }).click(); await sleep(1000)
check(await page.getByText('2FA on').count() > 0, '2FA turned on')
await page.getByRole('button', { name: 'Sign out' }).click(); await sleep(800)
await page.goto(BASE + '/login'); await sleep(600)
await page.fill('#email', 'analyst@example.org'); await page.fill('#password', 'Analyst2026'); await page.getByRole('button', { name: 'Sign in', exact: true }).click()
await page.waitForSelector('#otp', { timeout: 5000 }); await sleep(300)
await page.screenshot({ path: OUT + 'v11-2fa-login.png' })
await page.fill('#otp', totp(secret)); await page.getByRole('button', { name: 'Verify & sign in' }).click()
await page.waitForURL(/dashboard/, { timeout: 8000 })
check(true, 'signed in with 2FA code')

// password change
await page.goto(BASE + '/app/settings'); await sleep(1000)
await page.fill('#cpw', 'Analyst2026'); await page.fill('#npw', 'Analyst2027'); await page.fill('#npw2', 'Analyst2027')
await page.getByRole('button', { name: 'Update password' }).click(); await sleep(1200)
check(await page.locator('.toast').filter({ hasText: 'Password changed' }).count() > 0, 'password changed from Settings')
await page.goto(BASE + '/app/dashboard'); await sleep(800)
check(page.url().includes('/app/dashboard'), 'session continues after password change')

await browser.close()
console.log(errors.length ? `ERRORS (${errors.length}):\n` + errors.join('\n') : 'ALL v1.1 BROWSER CHECKS PASSED — no console / page / 5xx errors')
