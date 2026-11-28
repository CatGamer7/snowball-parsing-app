import { _electron as electron } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const token = process.env.SNOWBALL_E2E_TOKEN
const postId = process.env.SNOWBALL_E2E_SEED_POST
const rendererUrl = process.env.SNOWBALL_E2E_RENDERER_URL
delete process.env.SNOWBALL_E2E_TOKEN
delete process.env.SNOWBALL_E2E_SEED_POST
delete process.env.SNOWBALL_E2E_RENDERER_URL

let app
function requireCheck(condition, message) {
  if (!condition) throw new Error(message)
}

async function run() {
  requireCheck(
    token && postId && rendererUrl === 'http://127.0.0.1:5173',
    'Use npm run test:e2e:live'
  )
  const env = {}
  for (const [key, value] of Object.entries(process.env)) {
    if (
      value !== undefined &&
      !['ELECTRON_RUN_AS_NODE', 'ELECTRON_RENDERER_URL', 'DEBUG', 'PWDEBUG'].includes(
        key.toUpperCase()
      )
    )
      env[key] = value
  }
  env.ELECTRON_RENDERER_URL = rendererUrl
  app = await electron.launch({ args: ['.'], cwd: frontend, env })
  const page = await app.firstWindow()
  page.setDefaultTimeout(30_000)
  let rendererError = false
  page.on('pageerror', () => {
    rendererError = true
  })
  await page.getByRole('heading', { name: 'Параметры сбора' }).waitFor()

  // Без test runner, трассировки, скриншотов и отчётов. Значение ключа не становится
  // названием шага locator.fill и не передаётся в окружение Electron.
  await page.getByLabel('Токен доступа').waitFor()
  await page.evaluate((key) => {
    const field = document.getElementById('vk-token')
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
    if (!(field instanceof HTMLInputElement) || !setter) throw new Error('Token field unavailable')
    setter.call(field, key)
    field.dispatchEvent(new Event('input', { bubbles: true }))
  }, token)
  await page.getByRole('button', { name: 'Проверить токен' }).click()
  await page.getByText(/^(Сервисный ключ|Пользовательский токен) проверен$/).waitFor()
  console.log('PASS live token: real backend accepted the key through UI')

  await page.getByLabel('Тип', { exact: true }).selectOption('post')
  await page.getByLabel('Ссылка или ID').fill(postId)
  await page.getByRole('button', { name: 'Добавить', exact: true }).click()
  await page.getByRole('checkbox', { name: 'GLiNER multi v2.1' }).check()
  await page.getByLabel('Типы сущностей GLiNER').fill('person, organization, city')
  await page.getByLabel('Значение').fill('0.5')
  await page.getByLabel('Максимальная глубина').selectOption('1')
  const accepted = page.waitForResponse(
    (response) =>
      response.url() === 'http://127.0.0.1:8000/collection/start' &&
      response.request().method() === 'POST'
  )
  await page.getByRole('button', { name: 'Начать сбор' }).click()
  const response = await accepted
  requireCheck(response.status() === 202, `Start returned HTTP ${response.status()}`)
  const start = await response.json()
  requireCheck(
    typeof start.collection_id === 'string' && start.collection_id.length > 0,
    'Missing collection ID'
  )
  await page.getByRole('heading', { name: 'Извлечение данных' }).waitFor()
  console.log(`PASS live start: extraction screen opened; collection=${start.collection_id}`)

  const deadline = Date.now() + 300_000
  let lastPrint = 0
  while (Date.now() < deadline) {
    const status = await page.getByRole('status').innerText()
    if (status === 'Сбор завершён') break
    requireCheck(status !== 'Ошибка сбора', 'Real collection failed; inspect backend diagnostics')
    requireCheck(
      (await page.getByRole('alert').count()) === 0,
      'UI reported a progress request error'
    )
    if (Date.now() - lastPrint >= 10_000) {
      console.log(`Live UI status: ${status}`)
      lastPrint = Date.now()
    }
    await new Promise((resolve) => setTimeout(resolve, 1000))
  }
  requireCheck(
    (await page.getByRole('status').innerText()) === 'Сбор завершён',
    'Collection wait timed out; backend task may still be running'
  )
  const metric = (name) => page.getByText(name, { exact: true }).locator('..').locator('dd')
  const count = Number((await metric('Собрано записей').innerText()).replace(/\s/g, ''))
  requireCheck(Number.isSafeInteger(count) && count > 0, 'UI did not show collected records')
  const progressReply = await page.request.get(
    `http://127.0.0.1:8000/collection/${start.collection_id}/progress`
  )
  requireCheck(progressReply.status() === 200, 'Progress API is unavailable')
  const progress = await progressReply.json()
  requireCheck(
    progress.collection_id === start.collection_id &&
      progress.status === 'completed' &&
      progress.error === null &&
      progress.records_count === count,
    'UI and progress API do not agree'
  )
  requireCheck(
    ['max_depth', 'no_new_entities', 'no_new_records'].includes(progress.stop_reason),
    'Unexpected stop reason for a text-post GLiNER collection'
  )
  console.log(
    `PASS live progress: completed; records=${count}; stop_reason=${progress.stop_reason}`
  )

  const recordsReply = await page.request.get(
    `http://127.0.0.1:8000/collection/${start.collection_id}/records?limit=3`
  )
  requireCheck(recordsReply.status() === 200, 'Records API is unavailable')
  const records = await recordsReply.json()
  requireCheck(
    records.collection_id === start.collection_id &&
      records.total === count &&
      Array.isArray(records.items) &&
      records.items.length > 0 &&
      records.items.every((item) => typeof item.text === 'string' && item.text.trim()),
    'Collected posts are missing or counts do not agree'
  )
  console.log(`PASS live records: total=${records.total}; returned=${records.items.length}`)
  await page.getByRole('button', { name: 'К настройкам' }).click()
  await page.getByRole('heading', { name: 'Параметры сбора' }).waitFor()
  await page.getByLabel('Токен доступа').fill('')
  requireCheck(!rendererError, 'Renderer raised an unhandled JavaScript error')
  console.log('PASS live return: settings screen restored')
  console.log('RESULT: real Electron UI + backend + VK + GLiNER passed')
}

try {
  await run()
} catch (error) {
  const message = error instanceof Error ? error.message : 'Unknown live UI error'
  console.error(`FAIL live E2E: ${token ? message.split(token).join('[TOKEN]') : message}`)
  process.exitCode = 1
} finally {
  try {
    await app?.close()
  } catch {
    /* Keep the original test failure. */
  }
}
