import { join } from 'path'
import { _electron as electron } from '@playwright/test'
import type { ElectronApplication, Page } from '@playwright/test'
import { mockBackend, type RecordedRequest } from './mock-backend'

const FRONTEND_DIR = join(__dirname, '..', '..')

export interface RunningApp {
  app: ElectronApplication
  window: Page
  requests: RecordedRequest[]
  errors: string[]
}

/** Запускает собранное приложение (out/) с бэкендом-заглушкой. */
export async function launchApp(): Promise<RunningApp> {
  // Playwright принимает только строковые значения, а в process.env бывают undefined.
  const env: Record<string, string> = {}
  for (const [key, value] of Object.entries(process.env)) {
    if (value !== undefined && key !== 'ELECTRON_RENDERER_URL') env[key] = value
  }

  const app = await electron.launch({ args: ['.'], cwd: FRONTEND_DIR, env })
  const requests = await mockBackend(app.context())

  // Окно могло запросить список моделей до установки заглушки — перезагружаем его
  const window = await app.firstWindow()
  await window.reload()
  const errors: string[] = []
  window.on('pageerror', (error) => errors.push(error.message))
  window.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text())
  })
  await window.waitForLoadState('domcontentloaded')

  return { app, window, requests, errors }
}
