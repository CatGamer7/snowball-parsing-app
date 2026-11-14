import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  // Каждый тест-файл поднимает своё окно Electron, параллельно они мешают друг другу
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]]
})
