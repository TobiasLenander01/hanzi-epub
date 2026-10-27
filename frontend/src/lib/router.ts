import { useSyncExternalStore } from 'react'

export type Route =
  | { page: 'library' }
  | { page: 'read'; bookId: string; key: number | null }
  | { page: 'add'; libraryId: string | null }

export function parseRoute(hash: string): Route {
  const [page, a, b] = hash.replace(/^#\/?/, '').split('/')
  if (page === 'read' && a) return { page: 'read', bookId: a, key: b && /^\d+$/.test(b) ? Number(b) : null }
  if (page === 'add') return { page: 'add', libraryId: a || null }
  return { page: 'library' }
}

const subscribe = (cb: () => void) => {
  window.addEventListener('hashchange', cb)
  return () => window.removeEventListener('hashchange', cb)
}

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash)
  return parseRoute(hash)
}

export const href = {
  library: () => '#/',
  read: (bookId: string, key?: number) => `#/read/${bookId}${key === undefined ? '' : `/${key}`}`,
  add: (libraryId?: string) => `#/add${libraryId ? `/${libraryId}` : ''}`,
}

export function navigate(to: string, { replace = false } = {}) {
  if (replace) window.location.replace(to)
  else window.location.hash = to
}
