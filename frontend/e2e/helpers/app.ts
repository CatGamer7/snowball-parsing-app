import { join } from 'path'
import { _electron as electron } from '@playwright/test'
import type { ElectronApplication, Page } from '@playwright/test'
import { mockBackend, type MockBackendOptions, type RecordedRequest } from './mock-backend'

const FRONTEND_DIR = join(__dirname, '..', '..')

export interface RunningApp {
  app: ElectronApplication
  window: Page
  requests: RecordedRequest[]
  errors: string[]
}

/** Запускает собранное приложение (out/) с бэкендом-заглушкой. */
export async function launchApp(options: MockBackendOptions = {}): Promise<RunningApp> {
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
    const requests = await mockBackend(app.context(), options)
    const window = await app.firstWindow()
    // firstWindow сообщает о создании окна, но loadFile в main ещё может ожидать загрузку.
    // Ранняя reload отменяет эту навигацию и вызывает ERR_ABORTED в обработчике запуска.
    await window.waitForURL(
      (url) => url.protocol === 'file:' && url.pathname.endsWith('/out/renderer/index.html'),
      { waitUntil: 'load' }
    )
    const browserWindow = await app.browserWindow(window)
    try {
      // Подтверждаем завершение также в Electron main, а не только в CDP страницы.
      await browserWindow.evaluate(async ({ webContents }) => {
        if (webContents.isLoadingMainFrame()) {
          await new Promise<void>((resolve) => {
            webContents.once('did-finish-load', () => resolve())
          })
        }
      })
    } finally {
      await browserWindow.dispose()
    }
    const errors: string[] = []
    // Подписываемся до перезагрузки, чтобы не пропустить ошибки инициализации UI.
    window.on('pageerror', (error) => errors.push(error.message))
    window.on('console', (message) => {
      if (message.type() === 'error') errors.push(message.text())
    })

    // Первая загрузка могла начаться до установки заглушки.
    await window.reload({ waitUntil: 'load' })
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
