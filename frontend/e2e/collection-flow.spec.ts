import { expect, test } from '@playwright/test'
import { launchApp, type RunningApp } from './helpers/app'
import { MOCK } from './helpers/mock-backend'

// Экран «Параметры сбора» (SNO-5). Элементы ищутся по подписям и ролям, как их видит пользователь.

let run: RunningApp

test.beforeAll(async () => {
  run = await launchApp()
})

test.afterAll(async () => {
  await run?.app.close()
})

test('сбор от токена до запуска на mock-данных', async () => {
  const page = run.window
  const startButton = page.getByRole('button', { name: 'Начать сбор' })

  await test.step('1. Токен: неверный отклоняется, верный проходит', async () => {
    await expect(startButton).toBeDisabled()
    await page.getByLabel('Токен доступа').fill('vk1.a.wrong')
    await page.getByRole('button', { name: 'Проверить токен' }).click()
    await expect(page.getByText('Токен VK недействителен')).toBeVisible()

    await page.getByLabel('Токен доступа').fill(MOCK.validToken)
    await page.getByRole('button', { name: 'Проверить токен' }).click()
    await expect(page.getByText('Сервисный ключ проверен')).toBeVisible()
    await expect(startButton).toBeDisabled()
  })

  await test.step('2. Начальные записи', async () => {
    await page.getByLabel('Ссылка или ID').fill('https://vk.com/club1')
    await page.getByRole('button', { name: 'Добавить', exact: true }).click()
    await expect(
      page.getByRole('list', { name: 'Добавленные записи' }).getByRole('listitem')
    ).toHaveCount(1)

    await page.getByLabel('Ссылка или ID').fill('club1')
    await page.getByRole('button', { name: 'Добавить', exact: true }).click()
    await expect(page.getByText('Эта запись уже добавлена')).toBeVisible()
    await expect(
      page.getByRole('list', { name: 'Добавленные записи' }).getByRole('listitem')
    ).toHaveCount(1)
  })

  await test.step('3. Модель, типы сущностей и порог', async () => {
    await page.getByRole('checkbox', { name: MOCK.models[0].name }).check()
    await page.getByLabel('Типы сущностей GLiNER').fill('city')
    await page.getByLabel('Значение').fill('1.01')
    await expect(startButton).toBeDisabled()
    await page.getByLabel('Значение').fill('0.8')
    await expect(startButton).toBeEnabled()
    await startButton.click()
  })

  await test.step('4. В бэкенд ушли введённые параметры', async () => {
    await expect(page.getByRole('heading', { name: 'Извлечение данных' })).toBeVisible()

    const start = run.requests.find((r) => r.method === 'POST' && r.path === '/collection/start')
    expect(start?.body).toEqual({
      token: MOCK.validToken,
      seeds: [{ type: 'group', id: '1' }],
      rules: {
        models: { [MOCK.models[0].id]: { labels: ['city'] } },
        threshold: 0.8,
        max_depth: 2
      }
    })
  })

  await test.step('5. Экран процесса показывает завершение и возвращает к настройкам', async () => {
    await expect(page.getByRole('status')).toHaveText('Сбор завершён')
    expect(run.requests.some((r) => r.path === `/collection/${MOCK.collectionId}/progress`)).toBe(
      true
    )
    await page.getByRole('button', { name: 'К настройкам' }).click()
    await expect(page.getByRole('heading', { name: 'Параметры сбора' })).toBeVisible()
    await expect(page.getByLabel('Значение')).toHaveValue('0.8')
    await expect(page.getByRole('button', { name: 'Начать сбор' })).toBeEnabled()
  })

  await test.step('6. Изменённый токен требует повторной проверки', async () => {
    await page.getByLabel('Токен доступа').fill('vk1.a.other-token')
    await expect(page.getByText('Сервисный ключ проверен')).not.toBeVisible()
    await expect(page.getByRole('heading', { name: 'Извлечение данных' })).not.toBeVisible()
    await expect(page.getByRole('button', { name: 'Начать сбор' })).toBeDisabled()
    expect(
      run.requests.filter((r) => r.method === 'POST' && r.path === '/collection/start')
    ).toHaveLength(1)
  })
})
