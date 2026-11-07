import type { Seed } from './api'

export const MAX_SEEDS = 100

export function validateTokenInput(token: string): string | null {
  if (!token.trim()) {
    return 'Введите токен доступа'
  }

  if (/\s/.test(token)) {
    return 'Токен не должен содержать пробелы или переносы строк'
  }

  return null
}

export function parseSeed(type: Seed['type'], input: string): Seed {
  let value = input.trim()

  if (!value) {
    throw new Error('Введите ссылку или ID')
  }

  const isLink = /^https?:\/\//i.test(value) || /^(?:www\.|m\.)?vk\.(?:com|ru)\//i.test(value)

  if (isLink) {
    const address = /^https?:\/\//i.test(value) ? value : `https://${value}`

    let url: URL

    try {
      url = new URL(address)
    } catch {
      throw new Error('Некорректная ссылка')
    }

    const host = url.hostname.toLowerCase()
    const allowedHosts = ['vk.com', 'www.vk.com', 'm.vk.com', 'vk.ru', 'www.vk.ru', 'm.vk.ru']

    if (!allowedHosts.includes(host)) {
      throw new Error('Используйте ссылку на VK')
    }

    value = url.pathname.replace(/^\/+|\/+$/g, '')
  }

  if (type === 'post') {
    value = value.replace(/^wall/i, '')

    if (!/^-?[1-9]\d*_[1-9]\d*$/.test(value)) {
      throw new Error('Для поста укажите ссылку или ID вида -123_456')
    }

    return { type, id: value }
  }

  if (/^wall-?\d+_\d+$/i.test(value)) {
    throw new Error('Это ссылка на пост. Выберите тип «Пост»')
  }

  if (type === 'group') {
    if (/^id\d+$/i.test(value)) {
      throw new Error('Для этой записи выберите тип «Пользователь»')
    }

    value = value.replace(/^(?:club|public)(?=\d+$)/i, '')
  } else {
    if (/^(?:club|public)\d+$/i.test(value)) {
      throw new Error('Для этой записи выберите тип «Сообщество»')
    }

    value = value.replace(/^id(?=\d+$)/i, '')
  }

  if (!/^[a-zA-Z0-9_]+$/.test(value)) {
    throw new Error('Укажите ID или короткое имя из адреса VK')
  }

  if (/^\d+$/.test(value)) {
    value = value.replace(/^0+(?=\d)/, '')

    if (value === '0') {
      throw new Error('ID должен быть больше нуля')
    }
  }

  return { type, id: value }
}

export function seedKey(seed: Seed): string {
  return `${seed.type}:${seed.id.toLowerCase()}`
}

export function validateThreshold(input: string): number {
  const normalized = input.trim().replace(',', '.')
  const value = Number(normalized)

  if (!normalized || !Number.isFinite(value) || value < 0 || value > 1) {
    throw new Error('Введите значение от 0 до 1')
  }

  return value
}
