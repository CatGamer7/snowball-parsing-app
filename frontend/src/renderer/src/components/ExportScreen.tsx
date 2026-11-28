import { useEffect, useState } from 'react'
import { ApiError, getCollectionRecords } from '../api'
import type { CollectionProgress, CollectionRecord, CollectionRecords } from '../api'
import './export.css'

interface ExportScreenProps {
  progress: CollectionProgress
  seedCount: number
  maxDepth: number
  duration: string
  onBack: () => void
  onNewCollection: () => void
}

function postUrl(record: CollectionRecord): string {
  return `https://vk.com/wall${record.id}`
}

function csvCell(value: string): string {
  const safe = /^(?:[\t\r\n]|\s*[=+\-@＝＋－＠])/u.test(value) ? "'" + value : value
  return '"' + safe.replace(/"/g, '""') + '"'
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback
}

export default function ExportScreen({
  progress,
  seedCount,
  maxDepth,
  duration,
  onBack,
  onNewCollection
}: ExportScreenProps): React.JSX.Element {
  const [page, setPage] = useState<CollectionRecords | null>(null)
  const [offset, setOffset] = useState(0)
  const [showAll, setShowAll] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [retry, setRetry] = useState(0)
  const [includeSource, setIncludeSource] = useState(true)
  const [filename, setFilename] = useState('snowball_result.csv')
  const [withBom, setWithBom] = useState(false)
  const [delimiter, setDelimiter] = useState(',')
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [saved, setSaved] = useState<{ filename: string; folder: string; count: number } | null>(
    null
  )
  const limit = showAll ? 20 : 3

  useEffect(() => {
    const controller = new AbortController()
    void getCollectionRecords(progress.collection_id, offset, limit, controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setPage(result)
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setLoadError(errorMessage(error, 'Не удалось получить записи.'))
        }
      })
    return () => controller.abort()
  }, [progress.collection_id, offset, limit, retry])

  function resetPage(): void {
    setPage(null)
    setLoadError('')
  }

  function changePage(next: number): void {
    resetPage()
    setOffset(next)
  }

  async function save(): Promise<void> {
    if (saving || !page?.total) return
    const name = filename.trim()
    if (!name) {
      setSaveError('Введите имя файла.')
      return
    }

    setSaving(true)
    setSaveError('')
    setSaved(null)
    try {
      const rows = [includeSource ? ['Текст', 'Источник'] : ['Текст']]
      for (let from = 0; from < page.total; from += 100) {
        const batch = await getCollectionRecords(progress.collection_id, from, 100)
        if (batch.total !== page.total) {
          setSaveError(
            'Количество записей изменилось. Вернитесь к итогам и откройте экспорт заново.'
          )
          return
        }
        for (const record of batch.items) {
          rows.push(includeSource ? [record.text, postUrl(record)] : [record.text])
        }
      }

      const contents =
        (withBom ? '\uFEFF' : '') +
        rows.map((row) => row.map(csvCell).join(delimiter)).join('\r\n') +
        '\r\n'
      const result = await window.api.saveCsv(/\.csv$/i.test(name) ? name : name + '.csv', contents)
      if (result.status === 'saved') {
        setSaved({ filename: result.filename, folder: result.folder, count: page.total })
      } else if (result.status === 'error') {
        setSaveError(result.message)
      }
    } catch (error: unknown) {
      setSaveError(errorMessage(error, 'Не удалось сохранить CSV. Попробуйте ещё раз.'))
    } finally {
      setSaving(false)
    }
  }

  async function openFolder(): Promise<void> {
    try {
      if (await window.api.openExportFolder()) return
    } catch {
      // Show the same message if the folder cannot be opened.
    }
    setSaveError('Не удалось открыть папку.')
  }

  return (
    <main className="settings-page collection-page export-page">
      <h1>Экспорт результатов</h1>
      <p className="field-hint collection-step">Шаг 5 из 5</p>

      {saveError && (
        <div className="error-banner" role="alert">
          <strong>Ошибка экспорта</strong>
          <p>{saveError}</p>
        </div>
      )}
      {saved && (
        <div className="success-banner export-success" role="status">
          <strong>Файл сохранён</strong>
          <p>
            {saved.filename} · Записей: {saved.count} · {saved.folder}
          </p>
        </div>
      )}

      <section className="settings-card export-card" aria-label="Итоги сбора">
        <div className="collection-heading">
          <h2>{page?.total === 0 ? 'Сбор завершён: записей нет' : 'Сбор завершён'}</h2>
          <span className="field-hint">Время сбора: {duration}</span>
        </div>
        <dl className="collection-metrics export-metrics">
          {[
            ['Собрано записей', page?.total ?? progress.records_count],
            ['Достигнутая глубина', `${progress.expansion_level} из ${maxDepth}`],
            ['Запросов к VK API', progress.vk_requests_count],
            ['Начальных записей', seedCount]
          ].map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      {page?.total === 0 ? (
        <section className="settings-card export-card export-empty">
          <h2>Нет данных для экспорта</h2>
          <p className="field-hint">Попробуйте изменить начальные записи или параметры сбора.</p>
        </section>
      ) : (
        <>
          <section className="settings-card export-card">
            <h2>Что включить в файл</h2>
            <fieldset className="fields-group export-options" disabled={saving}>
              <legend className="visually-hidden">Столбцы CSV</legend>
              <label>
                <input type="checkbox" checked disabled /> Тексты записей (обязательно)
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={includeSource}
                  onChange={(event) => setIncludeSource(event.target.checked)}
                />{' '}
                Ссылка на источник
              </label>
            </fieldset>
          </section>

          <section className="settings-card export-card">
            <h2>Параметры файла</h2>
            <fieldset className="fields-group export-fields" disabled={saving}>
              <legend className="visually-hidden">Настройки CSV</legend>
              <label>
                <span className="field-label">Имя файла</span>
                <input
                  className="text-input"
                  value={filename}
                  maxLength={124}
                  onChange={(event) => setFilename(event.target.value)}
                />
              </label>
              <div>
                <span className="field-label">Папка сохранения</span>
                <p className="field-hint export-folder">
                  {saved?.folder ?? 'Выбирается в окне сохранения'}
                </p>
              </div>
              <label>
                <span className="field-label">Кодировка</span>
                <select
                  className="text-input"
                  value={withBom ? 'bom' : 'utf8'}
                  onChange={(event) => setWithBom(event.target.value === 'bom')}
                >
                  <option value="utf8">UTF-8</option>
                  <option value="bom">UTF-8 с BOM</option>
                </select>
              </label>
              <label>
                <span className="field-label">Разделитель</span>
                <select
                  className="text-input"
                  value={delimiter}
                  onChange={(event) => setDelimiter(event.target.value)}
                >
                  <option value=",">Запятая</option>
                  <option value=";">Точка с запятой</option>
                  <option value={'\t'}>Табуляция</option>
                </select>
              </label>
            </fieldset>
          </section>

          <section className="settings-card export-card">
            <div className="collection-heading">
              <h2>{showAll ? 'Собранные записи' : 'Предпросмотр (первые 3 строки)'}</h2>
              {page && (showAll || page.total > 3) && (
                <button
                  className="button-link"
                  type="button"
                  disabled={saving}
                  onClick={() => {
                    resetPage()
                    setOffset(0)
                    setShowAll(!showAll)
                  }}
                >
                  {showAll ? 'Первые 3 строки' : 'Все записи'}
                </button>
              )}
            </div>
            {loadError ? (
              <div role="alert">
                <p className="field-error">{loadError}</p>
                <button
                  className="button button-outline"
                  type="button"
                  onClick={() => {
                    resetPage()
                    setRetry((value) => value + 1)
                  }}
                >
                  Повторить запрос
                </button>
              </div>
            ) : page ? (
              <>
                <table className="export-table">
                  <thead>
                    <tr>
                      <th scope="col">Текст</th>
                      {includeSource && <th scope="col">Источник</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {page.items.map((record) => (
                      <tr key={record.id}>
                        <td className={showAll ? 'export-full-text' : 'export-preview-text'}>
                          {record.text}
                        </td>
                        {includeSource && (
                          <td>
                            <a href={postUrl(record)} target="_blank" rel="noreferrer">
                              Пост {record.id}
                            </a>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {showAll && (
                  <div className="collection-actions export-pagination">
                    <button
                      className="button button-outline"
                      type="button"
                      disabled={saving || offset === 0}
                      onClick={() => changePage(offset - limit)}
                    >
                      Назад
                    </button>
                    <span className="field-hint">
                      {offset + 1}–{offset + page.items.length} из {page.total}
                    </span>
                    <button
                      className="button button-outline"
                      type="button"
                      disabled={saving || offset + limit >= page.total}
                      onClick={() => changePage(offset + limit)}
                    >
                      Далее
                    </button>
                  </div>
                )}
              </>
            ) : (
              <p className="field-hint" role="status">
                Загружаем записи…
              </p>
            )}
          </section>
        </>
      )}

      <div className="collection-actions">
        <button
          className="button button-primary"
          type="button"
          disabled={saving || !page?.total}
          onClick={() => void save()}
        >
          {saving ? 'Готовим CSV…' : 'Сохранить CSV'}
        </button>
        {saved && (
          <button
            className="button button-outline"
            type="button"
            disabled={saving}
            onClick={() => void openFolder()}
          >
            Открыть папку
          </button>
        )}
        <button className="button button-outline" type="button" disabled={saving} onClick={onBack}>
          К итогам сбора
        </button>
        <button
          className="button button-outline"
          type="button"
          disabled={saving}
          onClick={onNewCollection}
        >
          Новый сбор
        </button>
      </div>
    </main>
  )
}
