import { expect, test } from '@playwright/test'
import { launchApp, type RunningApp } from './helpers/app'

let run: RunningApp

test.beforeAll(async () => {
  run = await launchApp()
})

test.afterAll(async () => {
  await run?.app.close()
})

test('приложение запускается и показывает окно', async () => {
  await expect(run.window.getByRole('heading', { name: 'Параметры сбора' })).toBeVisible()
  expect(await run.app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length)).toBe(
    1
  )
})

test('интерфейс получает ответы бэкенда-заглушки', async () => {
  const health = await run.window.evaluate(() =>
    fetch('http://127.0.0.1:8000/health').then((response) => response.json())
  )

  expect(health).toEqual({ status: 'ok' })
})

test('при запуске нет ошибок в консоли', async () => {
  expect(run.errors).toEqual([])
})
