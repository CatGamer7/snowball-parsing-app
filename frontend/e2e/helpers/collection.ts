import { expect } from '@playwright/test'
import type { Locator, Page } from '@playwright/test'
import { MOCK } from './mock-backend'

/** Настройка формы с искусственным токеном; реальные ключи в этот helper не передаются. */
export async function startMockCollection(page: Page): Promise<void> {
  await page.getByLabel('Токен доступа').fill(MOCK.validToken)
  await page.getByRole('button', { name: 'Проверить токен' }).click()
  await expect(page.getByText('Сервисный ключ проверен')).toBeVisible()
  await page.getByLabel('Ссылка или ID').fill('club1')
  await page.getByRole('button', { name: 'Добавить', exact: true }).click()
  await page.getByRole('checkbox', { name: MOCK.models[0].name }).check()
  await page.getByLabel('Типы сущностей GLiNER').fill('city')
  await page.getByLabel('Значение').fill('0.8')
  await page.getByRole('button', { name: 'Начать сбор' }).click()
  await expect(page.getByRole('heading', { name: 'Извлечение данных' })).toBeVisible()
}

export function metric(page: Page, name: string): Locator {
  return page.getByText(name, { exact: true }).locator('..').locator('dd')
}
