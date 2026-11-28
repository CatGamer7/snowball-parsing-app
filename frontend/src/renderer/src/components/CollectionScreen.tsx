import { useEffect, useState } from 'react'
import { ApiError, getCollectionProgress } from '../api'
import type { CollectionProgress } from '../api'
import ExportScreen from './ExportScreen'
import './collection.css'

interface CollectionScreenProps {
  collectionId: string
  seedCount: number
  threshold: number
  maxDepth: number
  onBack: () => void
}

const STATUS_LABELS = {
  queued: 'Задание в очереди',
  running: 'Идёт сбор',
  completed: 'Сбор завершён',
  failed: 'Ошибка сбора'
}

const STOP_REASONS = {
  max_depth: 'Достигнута максимальная глубина.',
  no_text_records: 'Не найдено записей с текстом.',
  no_new_entities: 'Новые сущности не найдены.',
  no_new_records: 'Новые записи не найдены.',
  record_limit: 'Достигнут лимит записей.'
}

const numbers = new Intl.NumberFormat('ru-RU')

function formatTime(from: string | null, to: string | null, now: number): string {
  if (!from) return '…'
  const seconds = Math.max(0, Math.floor(((to ? Date.parse(to) : now) - Date.parse(from)) / 1000))
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
    .map((part) => String(part).padStart(2, '0'))
    .join(':')
}

export default function CollectionScreen({
  collectionId,
  seedCount,
  threshold,
  maxDepth,
  onBack
}: CollectionScreenProps): React.JSX.Element {
  const [showExport, setShowExport] = useState(false)
  const [progress, setProgress] = useState<CollectionProgress | null>(null)
  const [requestError, setRequestError] = useState('')
  const [notFound, setNotFound] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [now, setNow] = useState(Date.now)

  const status = progress?.status
  const done = status === 'completed' || status === 'failed'
  const running = status === 'running'

  useEffect(() => {
    const controller = new AbortController()
    let timer: ReturnType<typeof setTimeout>

    async function poll(): Promise<void> {
      try {
        const next = await getCollectionProgress(collectionId, controller.signal)
        if (controller.signal.aborted) return
        setProgress(next)
        setNow(Date.now())
        if (next.status === 'queued' || next.status === 'running') {
          timer = setTimeout(() => void poll(), 1200)
        }
      } catch (cause: unknown) {
        if (controller.signal.aborted) return
        const missing = cause instanceof ApiError && cause.status === 404
        setNotFound(missing)
        setRequestError(
          cause instanceof ApiError ? cause.message : 'Не удалось получить состояние сбора'
        )
      }
    }

    void poll()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [collectionId, attempt])

  useEffect(() => {
    if (!running || requestError) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [running, requestError])

  const depth = progress?.expansion_level
  const metrics = [
    ['Собрано записей', progress?.records_count],
    ['Выбрано сущностей', progress?.selected_entities_count],
    ['Запросов к VK API', progress?.vk_requests_count],
    ['Начальных записей', seedCount]
  ] as const

  if (showExport && progress?.status === 'completed') {
    return (
      <ExportScreen
        progress={progress}
        seedCount={seedCount}
        maxDepth={maxDepth}
        duration={formatTime(progress.started_at, progress.finished_at, now)}
        onBack={() => setShowExport(false)}
        onNewCollection={onBack}
      />
    )
  }

  return (
    <main className="settings-page collection-page">
      <h1>Извлечение данных</h1>
      <p className="field-hint collection-step">Шаг 4 из 5</p>
      <ul className="collection-summary" aria-label="Параметры сбора">
        <li>Токен проверен</li>
        <li>Начальных записей: {seedCount}</li>
        <li>Порог уверенности: {numbers.format(threshold)}</li>
        <li>Максимальная глубина: {maxDepth}</li>
      </ul>

      {requestError && (
        <div className="collection-alert" role="alert">
          <strong>Не удалось обновить прогресс</strong>
          <p>{requestError}</p>
          {progress && <p>Показаны последние полученные данные.</p>}
        </div>
      )}

      {status === 'failed' && (
        <div className="collection-alert" role="alert">
          <strong>Сбор завершился с ошибкой</strong>
          <p>{progress?.error?.message ?? 'Бэкенд не сообщил причину ошибки.'}</p>
        </div>
      )}

      <section className="settings-card collection-card" aria-labelledby="collection-status">
        <div className="collection-heading">
          <h2 id="collection-status" role="status">
            {running && !requestError && <span className="collection-spinner" aria-hidden="true" />}
            {status
              ? STATUS_LABELS[status]
              : requestError
                ? 'Статус недоступен'
                : 'Получаем статус…'}
          </h2>
          <span className="field-hint">
            Время сбора:{' '}
            {formatTime(progress?.started_at ?? null, progress?.finished_at ?? null, now)}
          </span>
        </div>

        <label className="field-label" htmlFor="collection-depth">
          {depth === undefined ? 'Глубина сбора' : `Глубина ${depth} из ${maxDepth}`}
        </label>
        <progress
          id="collection-depth"
          className="collection-depth"
          max={maxDepth}
          value={depth === undefined ? 0 : Math.min(depth, maxDepth)}
        />

        <dl className="collection-metrics">
          {metrics.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value === undefined ? '…' : numbers.format(value)}</dd>
            </div>
          ))}
        </dl>

        {progress?.stop_reason && (
          <p className="field-hint">{STOP_REASONS[progress.stop_reason]}</p>
        )}

        <div className="collection-actions">
          {status === 'completed' && (
            <button
              className="button button-primary"
              type="button"
              onClick={() => setShowExport(true)}
            >
              Экспорт результатов
            </button>
          )}
          {requestError && !notFound && (
            <button
              className="button button-primary"
              type="button"
              onClick={() => {
                setRequestError('')
                setAttempt((value) => value + 1)
              }}
            >
              Повторить запрос
            </button>
          )}
          {done || notFound ? (
            <button className="button button-outline" type="button" onClick={onBack}>
              К настройкам
            </button>
          ) : !requestError ? (
            <>
              <button className="button button-primary" type="button" disabled>
                Пауза
              </button>
              <button className="button button-outline" type="button" disabled>
                Остановить
              </button>
              <span className="field-hint">Пауза и остановка пока недоступны.</span>
            </>
          ) : null}
        </div>
      </section>
    </main>
  )
}
