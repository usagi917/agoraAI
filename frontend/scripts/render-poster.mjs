import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { chromium } from '@playwright/test'

const source = resolve(process.argv[2] ?? '../poster/agent-ai-a4-print.html')
const output = resolve(process.argv[3] ?? '../output/pdf/agent-ai-a4-print.pdf')

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const page = await browser.newPage({ viewport: { width: 794, height: 1123 } })

await page.goto(pathToFileURL(source).href, { waitUntil: 'networkidle' })
await page.emulateMedia({ media: 'print' })
await page.evaluate(async () => {
  await document.fonts.ready
  await Promise.all(
    Array.from(document.images, (image) => {
      if (image.complete) return Promise.resolve()
      return new Promise((resolveImage, rejectImage) => {
        image.addEventListener('load', resolveImage, { once: true })
        image.addEventListener('error', rejectImage, { once: true })
      })
    }),
  )
})

await page.pdf({
  path: output,
  format: 'A4',
  preferCSSPageSize: true,
  printBackground: true,
  margin: { top: '0', right: '0', bottom: '0', left: '0' },
})

await browser.close()
console.log(output)
