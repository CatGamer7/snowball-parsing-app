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
    if (
      value !== undefined &&
      !['ELECTRON_RENDERER_URL', 'ELECTRON_RUN_AS_NODE'].includes(key.toUpperCase())
    ) {
      env[key] = value
    }
  }

  const app = await electron.launch({ args: ['.'], cwd: FRONTEND_DIR, env })
  try {
    const requests = await mockBackend(app.context())
    const window = await app.firstWindow()
    const errors: string[] = []
    // Подписываемся до перезагрузки, чтобы не пропустить ошибки инициализации UI.
    window.on('pageerror', (error) => errors.push(error.message))
    window.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text())
    })

    // Первая загрузка могла начаться до установки заглушки.
    await window.reload({ waitUntil: 'domcontentloaded' })
    return { app, window, requests, errors }
  } catch (error) {
    // beforeAll не вернёт RunningApp при ошибке настройки; закрываем процесс здесь.
    try {
      await app.close()
    } catch {
      // Процесс мог уже завершиться; сохраняем исходную ошибку настройки.
    }
    throw error
  }
}
