import type { BrowserContext, Route } from '@playwright/test'
import type { CollectionProgress } from '../../src/renderer/src/api/types'

// Используемые экраном ответы по контракту openapi.yaml 0.2.2 (SNO-9).
// При изменении контракта сверить заглушку и проверки отправляемого запроса в сценарии.
export const MOCK = {
  validToken: 'vk1.a.mock-valid-token',
  models: [
    {
      id: 'urchade/gliner_multi-v2.1',
      name: 'GLiNER multi v2.1',
      description: 'Извлечение сущностей с заданными пользователем типами. Основной вариант.',
      task: 'ner',
      settings_schema: {
        type: 'object',
        additionalProperties: false,
        required: ['labels'],
        properties: {
          labels: {
            type: 'array',
            minItems: 1,
            uniqueItems: true,
            items: { type: 'string', minLength: 1, pattern: '\\S' }
          }
        }
      }
    },
    {
      id: 'Babelscape/wikineural-multilingual-ner',
      name: 'WikiNEuRal multilingual NER',
      description:
        'Дополнительная NER-модель. Пользовательские настройки не предусмотрены. ' +
        'В текущем фоновом сборе эта модель ещё не подключена.',
      task: 'ner',
      settings_schema: { type: 'object', additionalProperties: false }
    }
  ],
  collectionId: 'mock-collection-1'
}

export interface RecordedRequest {
  method: string
  path: string
  body: unknown
}

export type ProgressReply = { status: number; json: unknown } | { abort: true }

export interface MockBackendOptions {
  progress?: (attempt: number) => ProgressReply | Promise<ProgressReply>
}

export function collectionProgress(
  status: CollectionProgress['status'],
  overrides: Partial<CollectionProgress> = {}
): CollectionProgress {
  const done = status === 'completed' || status === 'failed'
  return {
    collection_id: MOCK.collectionId,
    status,
    started_at: status === 'queued' ? null : '2026-11-28T10:00:00Z',
    finished_at: done ? '2026-11-28T10:01:05Z' : null,
    records_count: status === 'queued' ? 0 : status === 'completed' ? 79 : 59,
    expansion_level: status === 'completed' ? 2 : 0,
    selected_entities_count: status === 'completed' ? 1 : 0,
    vk_requests_count: status === 'queued' ? 3 : status === 'completed' ? 5 : 4,
    error: status === 'failed' ? { code: 'ML_NOT_AVAILABLE', message: 'Модель недоступна' } : null,
    stop_reason: status === 'completed' ? 'max_depth' : null,
    ...overrides
  }
}

const BACKEND_URL = /^http:\/\/(127\.0\.0\.1|localhost):\d+\//

// Окно открыто из file://, поэтому без CORS-заголовка fetch к бэкенду не пройдёт
const HEADERS = { 'access-control-allow-origin': '*', 'access-control-allow-headers': '*' }

function reply(route: Route, status: number, json: unknown): Promise<void> {
  return route.fulfill({ status, headers: HEADERS, json })
}

function error(route: Route, status: number, code: string, message: string): Promise<void> {
  return reply(route, status, { error: { code, message } })
}

export async function mockBackend(
  context: BrowserContext,
  options: MockBackendOptions = {}
): Promise<RecordedRequest[]> {
  const requests: RecordedRequest[] = []
  let progressRequests = 0

  await context.route(BACKEND_URL, async (route) => {
    const request = route.request()
    const method = request.method()
    const path = new URL(request.url()).pathname

    if (method === 'OPTIONS') return route.fulfill({ status: 204, headers: HEADERS })

    const body = request.postDataJSON() ?? null
    requests.push({ method, path, body })

    if (method === 'GET' && path === '/health') return reply(route, 200, { status: 'ok' })

    if (method === 'POST' && path === '/vk/validate') {
      return body?.token === MOCK.validToken
        ? reply(route, 200, { valid: true, token_type: 'service' })
        : error(route, 401, 'INVALID_TOKEN', 'Токен VK недействителен')
    }

    if (method === 'GET' && path === '/collection/models') {
      return reply(route, 200, MOCK.models)
    }

    if (method === 'POST' && path === '/collection/start') {
      progressRequests = 0
      return reply(route, 202, { collection_id: MOCK.collectionId, status: 'running' })
    }

    if (method === 'GET' && path === `/collection/${MOCK.collectionId}/progress`) {
      const result = options.progress
        ? await options.progress(progressRequests++)
        : { status: 200, json: collectionProgress('completed') }
      if ('abort' in result) return route.abort('failed')
      return reply(route, result.status, result.json)
    }

    return error(route, 404, 'NOT_MOCKED', `${method} ${path} нет в заглушке`)
  })

  return requests
}
