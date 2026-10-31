import type { BrowserContext, Route } from '@playwright/test'

// Ответы бэкенда-заглушки по контракту openapi.yaml 0.2.0 (SNO-9).
// При изменении контракта поправить только этот файл.
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
        'Дополнительная NER-модель. В этой версии пользовательские настройки не предусмотрены.',
      task: 'ner',
      settings_schema: { type: 'object', additionalProperties: false }
    }
  ],
  collectionId: 'mock-collection-1',
  // Точки статуса и результатов в контракте 0.2.0 ещё нет, путь /collection/<id> условный
  result: {
    status: 'finished',
    items: [
      { text: 'Студенты ТПУ провели форум в Москве.', depth: 0 },
      { text: 'На форуме обсудили языковые модели.', depth: 1 }
    ]
  }
}

export interface RecordedRequest {
  method: string
  path: string
  body: unknown
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

export async function mockBackend(context: BrowserContext): Promise<RecordedRequest[]> {
  const requests: RecordedRequest[] = []

  await context.route(BACKEND_URL, (route) => {
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
      return reply(route, 202, { collection_id: MOCK.collectionId, status: 'running' })
    }

    if (method === 'GET' && path === `/collection/${MOCK.collectionId}`) {
      return reply(route, 200, MOCK.result)
    }

    return error(route, 404, 'NOT_MOCKED', `${method} ${path} нет в заглушке`)
  })

  return requests
}
