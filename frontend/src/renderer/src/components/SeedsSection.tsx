import { useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import type { Seed } from '../api'
import { MAX_SEEDS, parseSeed, seedKey } from '../validation'

interface SeedsSectionProps {
  seeds: Seed[]
  disabled: boolean
  onSeedsChange: (seeds: Seed[]) => void
}

const TYPE_NAMES: Record<Seed['type'], string> = {
  group: 'Сообщество',
  user: 'Пользователь',
  post: 'Пост'
}

export default function SeedsSection({
  seeds,
  disabled,
  onSeedsChange
}: SeedsSectionProps): React.JSX.Element {
  const [type, setType] = useState<Seed['type']>('group')
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [importing, setImporting] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const locked = disabled || importing

  function addSeed(): void {
    setError('')
    setNotice('')

    try {
      const seed = parseSeed(type, input)

      if (seeds.some((item) => seedKey(item) === seedKey(seed))) {
        throw new Error('Эта запись уже добавлена')
      }

      if (seeds.length >= MAX_SEEDS) {
        throw new Error(`Можно добавить не больше ${MAX_SEEDS} записей`)
      }

      onSeedsChange([...seeds, seed])
      setInput('')
      setNotice('Запись добавлена')
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'Не удалось добавить запись')
    }
  }

  function removeSeed(index: number): void {
    onSeedsChange(seeds.filter((_, position) => position !== index))
    setError('')
    setNotice('Запись удалена')
  }

  async function importFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    const file = event.target.files?.[0]
    event.target.value = ''

    if (!file) return

    setError('')
    setNotice('')

    if (!file.name.toLowerCase().endsWith('.txt')) {
      setError('Выберите файл в формате .txt')
      return
    }

    if (file.size > 1_000_000) {
      setError('Размер файла не должен превышать 1 МБ')
      return
    }

    setImporting(true)

    try {
      const text = await file.text()
      const lines = text
        .replace(/^\uFEFF/, '')
        .split(/\r?\n/)
        .map((line, index) => ({
          value: line.trim(),
          number: index + 1
        }))
        .filter((line) => line.value.length > 0)

      if (lines.length === 0) {
        throw new Error('Файл пуст')
      }

      const next = [...seeds]
      const keys = new Set(next.map(seedKey))
      let added = 0
      let duplicates = 0

      for (const line of lines) {
        let seed: Seed

        try {
          seed = parseSeed(type, line.value)
        } catch (caught: unknown) {
          const message = caught instanceof Error ? caught.message : 'Неверная запись'

          throw new Error(`Строка ${line.number}: ${message}`)
        }

        const key = seedKey(seed)

        if (keys.has(key)) {
          duplicates += 1
          continue
        }

        if (next.length >= MAX_SEEDS) {
          throw new Error(`Слишком много записей. Максимум — ${MAX_SEEDS}. Импорт отменён`)
        }

        next.push(seed)
        keys.add(key)
        added += 1
      }

      onSeedsChange(next)
      setNotice(`Добавлено: ${added}. Пропущено повторов: ${duplicates}`)
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : 'Не удалось прочитать файл')
    } finally {
      setImporting(false)
    }
  }

  return (
    <section className="settings-card" aria-labelledby="seeds-heading">
      <h2 id="seeds-heading">2. Начальные записи</h2>

      <fieldset className="fields-group" disabled={locked}>
        <legend className="visually-hidden">Добавление начальных записей</legend>

        <div className="seed-entry-row">
          <div>
            <label className="field-label" htmlFor="seed-type">
              Тип
            </label>

            <select
              id="seed-type"
              className="text-input"
              value={type}
              onChange={(event) => {
                setType(event.target.value as Seed['type'])
                setError('')
                setNotice('')
              }}
            >
              <option value="group">Сообщество</option>
              <option value="user">Пользователь</option>
              <option value="post">Пост</option>
            </select>
          </div>

          <div>
            <label className="field-label" htmlFor="seed-input">
              Ссылка или ID
            </label>

            <input
              id="seed-input"
              className={`text-input ${error ? 'input-error' : ''}`}
              value={input}
              placeholder="vk.com/club123"
              aria-invalid={Boolean(error)}
              aria-describedby="seed-feedback seed-examples"
              onChange={(event) => {
                setInput(event.target.value)
                setError('')
                setNotice('')
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  addSeed()
                }
              }}
            />
          </div>

          <button className="button button-primary" type="button" onClick={addSeed}>
            Добавить
          </button>
        </div>

        <div id="seed-feedback" aria-live="polite">
          {error && <p className="field-error">{error}</p>}
          {notice && <p className="field-success">{notice}</p>}
        </div>

        <p id="seed-examples" className="field-hint">
          Примеры: vk.com/club123, vk.com/wall-123_456, vk.com/id123
        </p>

        <ul className="seed-list" aria-label="Добавленные записи">
          {seeds.map((seed, index) => (
            <li className="seed-item" key={seedKey(seed)}>
              <span className="seed-type">{TYPE_NAMES[seed.type]}</span>
              <span className="seed-id">{seed.id}</span>
              <span className="field-hint">Добавлена</span>

              <button
                className="remove-button"
                type="button"
                aria-label={`Удалить запись ${seed.id}`}
                onClick={() => removeSeed(index)}
              >
                ×
              </button>
            </li>
          ))}
        </ul>

        {seeds.length === 0 && <p className="field-hint">Добавьте хотя бы одну начальную запись</p>}

        <div className="section-footer">
          <span className="field-hint">
            Добавлено: {seeds.length} из {MAX_SEEDS}
          </span>

          <button className="button-link" type="button" onClick={() => fileInput.current?.click()}>
            {importing ? 'Импортируем…' : 'Импорт из файла (.txt)'}
          </button>
        </div>

        <input
          ref={fileInput}
          className="visually-hidden"
          type="file"
          accept=".txt,text/plain"
          aria-label="Файл с начальными записями"
          onChange={(event) => void importFile(event)}
        />

        <p className="field-hint">
          Для импорта выберите тип выше. В файле — одна запись на строку, все записи выбранного
          типа. Доступность проверится при запуске.
        </p>
      </fieldset>
    </section>
  )
}
