import { expect, test } from '@playwright/test'
import { launchApp, type RunningApp } from './helpers/app'
import { MOCK } from './helpers/mock-backend'

// Элементы ищутся по data-testid (список в e2e/README.md). Пока экранов нет, тест пропускается.

let run: RunningApp

test.beforeAll(async () => {
  run = await launchApp()
})

test.afterAll(async () => {
  await run?.app.close()
})

test('сбор от токена до результата на mock-данных', async () => {
  const page = run.window
  test.skip(
    (await page.getByTestId('token-input').count()) === 0,
    'Экрана токена ещё нет в интерфейсе'
  )

  await test.step('1. Токен: неверный отклоняется, верный проходит', async () => {
    await page.getByTestId('token-input').fill('vk1.a.wrong')
    await page.getByTestId('token-check').click()
    await expect(page.getByTestId('token-error')).toBeVisible()
    await expect(page.getByTestId('token-next')).toBeDisabled()

    await page.getByTestId('token-input').fill(MOCK.validToken)
    await page.getByTestId('token-check').click()
    await expect(page.getByTestId('token-next')).toBeEnabled()
    await page.getByTestId('token-next').click()
  })

  await test.step('2. Начальные записи', async () => {
    await page.getByTestId('seed-input').fill('https://vk.com/club1')
    await page.getByTestId('seed-add').click()
    await expect(page.getByTestId('seed-item')).toHaveCount(1)
    await page.getByTestId('seeds-next').click()
  })

  await test.step('3. Модель, типы сущностей и порог', async () => {
    await page.getByTestId('model-select').selectOption(MOCK.models[0].id)
    await page.getByTestId('labels-input').fill('city')
    await page.getByTestId('threshold-input').fill('0.8')
    await page.getByTestId('collection-start').click()
  })

  await test.step('4. В бэкенд ушли введённые параметры', async () => {
    const start = run.requests.find((r) => r.method === 'POST' && r.path === '/collection/start')
    expect(start, 'запрос /collection/start не отправлен').toBeTruthy()

    // Проверяем значения, а не полную структуру запроса
    const body = JSON.stringify(start?.body)
    for (const value of [MOCK.validToken, '"type":"group"', MOCK.models[0].id, 'city', '0.8']) {
      expect(body).toContain(value)
    }
  })

  await test.step('5. Показан mock-результат', async () => {
    await expect(page.getByTestId('result-item')).toHaveCount(MOCK.result.items.length)
    await expect(page.getByTestId('result-item').first()).toContainText(MOCK.result.items[0].text)
  })
})
