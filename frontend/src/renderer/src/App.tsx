import { useState } from 'react'
import { ApiError, checkHealth, getModels } from './api'

function App(): React.JSX.Element {
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

      <pre>{result}</pre>
    </main>
  )
}

export default App