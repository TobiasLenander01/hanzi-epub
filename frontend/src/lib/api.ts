export type Chapter = {
  index: number
  title: string
  part: string
  word_count: number
  start_page: number
  end_page: number
  preview: string
}

export type BookInfo = {
  id: string
  title: string
  author: string
  has_cover: boolean
  total_pages: number
  words_per_page: number
  word_count: number
  translated: Record<Script, number[]>
  chapters: Chapter[]
}

export type Health = {
  ok: boolean
  model: string
  api_ready: boolean
  api_message: string
}

export type Script = 'simplified' | 'traditional'

export type Selection =
  | { mode: 'chapters'; chapters: number[] }
  | { mode: 'pages'; page_start: number; page_end: number }

export type PreviewPair = { id: number; en: string; html: string }

export type JobSnapshot = {
  id: string
  status: 'running' | 'done' | 'error' | 'cancelled'
  stage: 'preparing' | 'translating' | 'done'
  total: number
  done: number
  error: string
  library_id: string
  saved: number[]
  preview: PreviewPair[]
  stats: {
    sentences?: number
    translated?: number
    chapters?: number
    characters?: number
    unique_characters?: number
  }
  elapsed: number
}

// ---------- Library ----------

export type Converting = { job_id: string; done: number; total: number } | null

export type LibraryBook = {
  id: string
  title: string
  title_zh: string
  author: string
  script: Script
  has_cover: boolean
  source_chapters: number
  keys: number[]
  sentences: number
  characters: number
  updated: number
  converting: Converting
}

export type ChapterSummary = {
  key: number
  title_en: string
  title_zh: string
  title_html: string
  part: string
  partial: boolean
  sentences: number
  characters: number
}

export type BookMeta = {
  id: string
  title: string
  title_zh: string
  title_html: string
  author: string
  script: Script
  lang: string
  source_chapters: number
  cover: string | null
  chapters: ChapterSummary[]
  converting: Converting
}

export type PairData = { en: string; zh: string; html: string }
export type BodyBlock = ({ kind: 'heading' } & PairData) | { kind: 'para'; pairs: PairData[] }
export type ChapterData = ChapterSummary & { body: BodyBlock[] }

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
  } catch {
    /* not JSON */
  }
  return `Request failed (${res.status})`
}

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}

export const getLibrary = () => getJson<LibraryBook[]>('/api/library')
export const getBookMeta = (id: string) => getJson<BookMeta>(`/api/library/${id}`)
export const getChapter = (id: string, key: number) => getJson<ChapterData>(`/api/library/${id}/chapters/${key}`)
export const deleteBook = (id: string) => getJson<{ ok: boolean }>(`/api/library/${id}`, { method: 'DELETE' })
export const openSource = (id: string) => getJson<BookInfo>(`/api/library/${id}/source`, { method: 'POST' })
export const libraryCoverUrl = (id: string) => `/api/library/${id}/cover`
export const libraryEpubUrl = (id: string) => `/api/library/${id}/epub`

export async function getHealth(): Promise<Health> {
  const res = await fetch('/api/health')
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}

export async function uploadBook(file: File): Promise<BookInfo> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/api/books', { method: 'POST', body: form })
  if (!res.ok) throw new Error(await errorMessage(res))
  return res.json()
}

export async function startConversion(bookId: string, selection: Selection, script: Script): Promise<string> {
  const res = await fetch(`/api/books/${bookId}/convert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...selection, script }),
  })
  if (!res.ok) throw new Error(await errorMessage(res))
  return (await res.json()).job_id
}

export function watchJob(jobId: string, onUpdate: (snap: JobSnapshot) => void): () => void {
  const source = new EventSource(`/api/jobs/${jobId}/events`)
  source.onmessage = (event) => {
    const snap: JobSnapshot = JSON.parse(event.data)
    onUpdate(snap)
    if (snap.status !== 'running') source.close()
  }
  return () => source.close()
}

export async function cancelJob(jobId: string): Promise<void> {
  await fetch(`/api/jobs/${jobId}/cancel`, { method: 'POST' })
}

export const coverUrl = (uploadId: string) => `/api/books/${uploadId}/cover`

/** Rough planning numbers for Claude Haiku 5.5 ($0.10 / $0.50 per million tokens). */
export function estimate(words: number) {
  const sentences = Math.max(1, Math.round(words / 15))
  const batches = Math.ceil(words / 400)
  const inputTokens = words * 1.4 + batches * 700
  const outputTokens = words * 2.4
  const cost = (inputTokens * 0.1 + outputTokens * 0.5) / 1_000_000
  const seconds = Math.max(8, (batches / 6) * 16 + 8)
  return { sentences, cost, seconds }
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds / 5) * 5 || 5} sec`
  const minutes = Math.round(seconds / 60)
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

export function formatCost(cost: number): string {
  if (cost < 0.01) return '< $0.01'
  return `$${cost.toFixed(2)}`
}
