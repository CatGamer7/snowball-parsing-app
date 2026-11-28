import { expect, test, type Page } from '@playwright/test'
import type { CollectionProgress } from '../src/renderer/src/api/types'
import { launchApp, type RunningApp } from './helpers/app'
import { metric, startMockCollection } from './helpers/collection'
import { collectionProgress, MOCK, type MockBackendOptions } from './helpers/mock-backend'

let run: RunningApp | undefined

test.afterEach(async () => {
  const current = run
  run = undefined
  await current?.app.close()
})

async function openScreen(options: MockBackendOptions = {}): Promise<Page> {
  const current = await launchApp(options)
  run = current
  await startMockCollection(current.window)
  return current.window
}

function polls(): number {
  if (!run) throw new Error('Test application has not been launched')
  return run.requests.filter(
    (request) => request.path === `/collection/${MOCK.collectionId}/progress`
  ).length
}

test('очередь → сбор → завершение: параметры, метрики, глубина и остановка опроса', async () => {
  let state: CollectionProgress['status'] = 'queued'
  const page = await openScreen({
    progress: () => ({ status: 200, json: collectionProgress(state) })
  })
  await expect(page.getByRole('status')).toHaveText('Задание в очереди')
  const summary = page.getByRole('list', { name: 'Параметры сбора' })
  await expect(summary).toContainText('Начальных записей: 1')
  await expect(summary).toContainText('Порог уверенности: 0,8')
  await expect(summary).toContainText('Максимальная глубина: 2')
  await expect(metric(page, 'Собрано записей')).toHaveText('0')
  await expect(page.getByRole('button', { name: 'Пауза', exact: true })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Остановить', exact: true })).toBeDisabled()

  state = 'running'
  await expect(page.getByRole('status')).toHaveText('Идёт сбор')
  await expect(metric(page, 'Собрано записей')).toHaveText('59')
  await expect(metric(page, 'Запросов к VK API')).toHaveText('4')
  await expect(page.getByLabel('Глубина 0 из 2')).toHaveAttribute('value', '0')

  state = 'completed'
  await expect(page.getByRole('status')).toHaveText('Сбор завершён')
  await expect(metric(page, 'Собрано записей')).toHaveText('79')
  await expect(metric(page, 'Выбрано сущностей')).toHaveText('1')
  await expect(metric(page, 'Запросов к VK API')).toHaveText('5')
  await expect(metric(page, 'Начальных записей')).toHaveText('1')
  await expect(page.getByLabel('Глубина 2 из 2')).toHaveAttribute('value', '2')
  await expect(page.getByText('Время сбора: 00:01:05')).toBeVisible()
  await expect(page.getByText('Достигнута максимальная глубина.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'К настройкам' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Пауза', exact: true })).toHaveCount(0)

  const finishedPolls = polls()
  // Нужен период наблюдения длиннее интервала 1200 мс: проверяем отсутствие нового запроса.
  await page.waitForTimeout(1600)
  expect(polls()).toBe(finishedPolls)
})

for (const [code, message] of [
  ['ML_NOT_AVAILABLE', 'Выбранная модель пока не подключена'],
  ['VK_ERROR', 'Не удалось продолжить сбор из VK']
] as const) {
  test(`ошибка ${code}: сообщение, частичные счётчики и возврат`, async () => {
    const page = await openScreen({
      progress: () => ({
        status: 200,
        json: collectionProgress('failed', { error: { code, message }, records_count: 12 })
      })
    })
    await expect(page.getByRole('status')).toHaveText('Ошибка сбора')
    await expect(page.getByRole('alert')).toContainText(message)
    await expect(metric(page, 'Собрано записей')).toHaveText('12')
    await expect(page.getByRole('button', { name: 'Повторить запрос' })).toHaveCount(0)
    await page.getByRole('button', { name: 'К настройкам' }).click()
    await expect(page.getByRole('heading', { name: 'Параметры сбора' })).toBeVisible()
    await expect(page.getByLabel('Значение')).toHaveValue('0.8')
  })
}

test('ошибка обновления сохраняет последние данные и восстанавливается по кнопке', async () => {
  let phase: 'running' | 'error' | 'completed' = 'running'
  const page = await openScreen({
    progress: () =>
      phase === 'error'
        ? {
            status: 502,
            json: { error: { code: 'VK_UNAVAILABLE', message: 'Тестовая ошибка связи' } }
          }
        : { status: 200, json: collectionProgress(phase) }
  })
  await expect(metric(page, 'Собрано записей')).toHaveText('59')
  phase = 'error'
  await expect(page.getByRole('alert')).toContainText('Не удалось обновить прогресс')
  await expect(page.getByText('Показаны последние полученные данные.')).toBeVisible()
  await expect(metric(page, 'Собрано записей')).toHaveText('59')
  const stoppedPolls = polls()
  await page.waitForTimeout(1600)
  expect(polls()).toBe(stoppedPolls)
  phase = 'completed'
  await page.getByRole('button', { name: 'Повторить запрос' }).click()
  await expect(page.getByRole('status')).toHaveText('Сбор завершён')
  await expect(metric(page, 'Собрано записей')).toHaveText('79')
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('404 задания: статус недоступен, повтор отсутствует, возврат доступен', async () => {
  const page = await openScreen({
    progress: () => ({
      status: 404,
      json: { error: { code: 'COLLECTION_NOT_FOUND', message: 'Задание не найдено' } }
    })
  })
  await expect(page.getByRole('status')).toHaveText('Статус недоступен')
  await expect(page.getByRole('alert')).toContainText('Задание не найдено')
  await expect(page.getByRole('button', { name: 'Повторить запрос' })).toHaveCount(0)
  await page.getByRole('button', { name: 'К настройкам' }).click()
  await expect(page.getByRole('heading', { name: 'Параметры сбора' })).toBeVisible()
})

test('обрыв сети при первом запросе прогресса и успешный повтор', async () => {
  let offline = true
  const page = await openScreen({
    progress: () =>
      offline ? { abort: true } : { status: 200, json: collectionProgress('completed') }
  })
  await expect(page.getByRole('alert')).toContainText('Не удалось подключиться к серверу')
  await expect(page.getByRole('status')).toHaveText('Статус недоступен')
  offline = false
  await page.getByRole('button', { name: 'Повторить запрос' }).click()
  await expect(page.getByRole('status')).toHaveText('Сбор завершён')
})

for (const [name, overrides] of [
  ['отрицательный счётчик', { records_count: -1 }],
  ['чужой collection_id', { collection_id: 'another-task' }]
] as const) {
  test(`неверный ответ API: ${name}`, async () => {
    const page = await openScreen({
      progress: () => ({ status: 200, json: collectionProgress('running', overrides) })
    })
    await expect(page.getByRole('alert')).toContainText(
      'Ответ сервера не соответствует API-контракту'
    )
    await expect(page.getByRole('status')).toHaveText('Статус недоступен')
    await expect(metric(page, 'Собрано записей')).toHaveText('…')
    await expect(page.getByRole('button', { name: 'Повторить запрос' })).toBeVisible()
  })
}

test('уход с экрана прекращает опрос старого задания', async () => {
  const page = await openScreen({
    progress: () => ({ status: 200, json: collectionProgress('running') })
  })
  await expect(page.getByRole('status')).toHaveText('Идёт сбор')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'Параметры сбора' })).toBeVisible()
  const previousPolls = polls()
  await page.waitForTimeout(1600)
  expect(polls()).toBe(previousPolls)
})

for (const [reason, message] of [
  ['no_text_records', 'Не найдено записей с текстом.'],
  ['no_new_entities', 'Новые сущности не найдены.'],
  ['no_new_records', 'Новые записи не найдены.'],
  ['record_limit', 'Достигнут лимит записей.']
] as const) {
  test(`причина завершения: ${reason}`, async () => {
    const page = await openScreen({
      progress: () => ({
        status: 200,
        json: collectionProgress('completed', {
          stop_reason: reason,
          records_count: reason === 'no_text_records' ? 0 : reason === 'record_limit' ? 5000 : 59,
          expansion_level: reason === 'no_text_records' || reason === 'no_new_entities' ? 0 : 1,
          selected_entities_count:
            reason === 'no_text_records' || reason === 'no_new_entities' ? 0 : 1
        })
      })
    })
    await expect(page.getByRole('status')).toHaveText('Сбор завершён')
    await expect(page.getByText(message, { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: 'К настройкам' })).toBeVisible()
  })
}
