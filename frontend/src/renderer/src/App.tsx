import { useState } from 'react'
import { ApiError, checkHealth, getModels, startCollection, validateToken } from './api'
import type { Seed } from './api'

function App(): React.JSX.Element {
  const [token, setToken] = useState('')
  const [seedType, setSeedType] = useState<Seed['type']>('group')
  const [seedId, setSeedId] = useState('')
  const [result, setResult] = useState('Нажмите кнопку для проверки')
  const [loading, setLoading] = useState(false)

  async function run(action: () => Promise<unknown>): Promise<void> {
    setLoading(true)
    setResult('Загрузка…')

    try {
      const data = await action()
      setResult(JSON.stringify(data, null, 2) ?? 'Пустой ответ')
    } catch (error: unknown) {
      if (error instanceof ApiError) {
        setResult(
          [
            `Ошибка: ${error.kind}`,
            error.message,
            error.status ? `HTTP: ${error.status}` : '',
            error.code ? `Код: ${error.code}` : ''
          ]
            .filter(Boolean)
            .join('\n')
        )
      } else {
        setResult('Произошла непредвиденная ошибка')
      }
    } finally {
      setLoading(false)
    }
  }

  function testStart(): void {
    void run(() =>
      startCollection({
        token: token.trim(),
        seeds: [{ type: seedType, id: seedId.trim() }],
        rules: {
          models: {
            'urchade/gliner_multi-v2.1': {
              labels: ['person', 'organization', 'city']
            }
          },
          threshold: 0.5,
          max_depth: 2
        }
      })
    )
  }

  return (
    <main className="app">
      <h1>Snowball — проверка API</h1>

      <p>
        <button disabled={loading} onClick={() => void run(checkHealth)}>
          Проверить сервер
        </button>{' '}
        <button disabled={loading} onClick={() => void run(getModels)}>
          Получить модели
        </button>
      </p>

      <p>
        <label>
          Токен VK:{' '}
          <input
            type="password"
            autoComplete="off"
            value={token}
            disabled={loading}
            onChange={(event) => setToken(event.target.value)}
          />
        </label>{' '}
        <button
          disabled={loading || !token.trim()}
          onClick={() => void run(() => validateToken({ token: token.trim() }))}
        >
          Проверить токен
        </button>
      </p>

      <p>
        <label>
          Тип источника:{' '}
          <select
            value={seedType}
            disabled={loading}
            onChange={(event) => setSeedType(event.target.value as Seed['type'])}
          >
            <option value="group">Сообщество</option>
            <option value="user">Пользователь</option>
            <option value="post">Пост</option>
          </select>
        </label>
      </p>

      <p>
        <label>
          ID источника без ссылки:{' '}
          <input
            value={seedId}
            disabled={loading}
            onChange={(event) => setSeedId(event.target.value)}
          />
        </label>{' '}
        <button disabled={loading || !token.trim() || !seedId.trim()} onClick={testStart}>
          Проверить запуск
        </button>
      </p>

      <p>Для теста выбрана GLiNER. Настоящий сбор на бэкенде пока не подключён.</p>

      <pre>{result}</pre>
    </main>
  )
}

export default App
