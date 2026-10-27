import { useSyncExternalStore } from 'react'

/** A tiny persisted store: state lives in localStorage and every subscriber re-renders on change. */
export function createStore<T>(key: string, initial: () => T) {
  let state: T = initial()
  try {
    const saved = localStorage.getItem(key)
    if (saved) state = { ...state, ...JSON.parse(saved) }
  } catch {
    /* storage unavailable or corrupt: keep defaults */
  }
  const listeners = new Set<() => void>()

  const set = (next: T | ((prev: T) => T)) => {
    state = typeof next === 'function' ? (next as (prev: T) => T)(state) : next
    try {
      localStorage.setItem(key, JSON.stringify(state))
    } catch {
      /* ignore */
    }
    listeners.forEach((l) => l())
  }

  const subscribe = (l: () => void) => {
    listeners.add(l)
    return () => listeners.delete(l)
  }

  const use = () => useSyncExternalStore(subscribe, () => state)
  return { get: () => state, set, use, subscribe }
}

// ---------- Theme ----------

export type Theme = 'light' | 'dark'

const systemDark = window.matchMedia('(prefers-color-scheme: dark)')
export const themeStore = createStore<{ theme: Theme | null }>('hanzi-theme', () => ({ theme: null }))

export const resolvedTheme = (): Theme => themeStore.get().theme ?? (systemDark.matches ? 'dark' : 'light')

function applyTheme() {
  const theme = resolvedTheme()
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.style.colorScheme = theme
}
applyTheme()
themeStore.subscribe(applyTheme)
systemDark.addEventListener('change', applyTheme)

export function useTheme(): [Theme, (t: Theme) => void] {
  themeStore.use()
  return [resolvedTheme(), (theme) => themeStore.set({ theme })]
}

// ---------- Reader settings ----------

export const TEXT_SIZES = [0.85, 0.93, 1, 1.1, 1.22, 1.36]

export type ReaderSettings = { size: number; pinyin: boolean; english: boolean }
export const readerSettings = createStore<ReaderSettings>('hanzi-reader-settings', () => ({
  size: 2,
  pinyin: true,
  english: true,
}))

// ---------- Reading progress ----------

/** Where a book was left: chapter key and paragraph index (`block`, absent in older saves). */
export type Progress = { key: number; block?: number; fraction: number; at: number }
export const progressStore = createStore<Record<string, Progress>>('hanzi-progress', () => ({}))

export function saveProgress(bookId: string, key: number, block: number, blocks: number) {
  const fraction = blocks > 0 ? block / blocks : 0
  progressStore.set((all) => ({ ...all, [bookId]: { key, block, fraction, at: Date.now() } }))
}
