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
  stage: 'preparing' | 'translating' | 'packaging' | 'done'
  total: number
  done: number
  error: string
  preview: PreviewPair[]
  stats: {
    sentences?: number
    translated?: number
    chapters?: number
    characters?: number
    unique_characters?: number
    size_kb?: number
  }
  filename: string
  elapsed: number
}

async function errorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') return body.detail
  } catch {
    /* not JSON */
  }
  return `Request failed (${res.status})`
}

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

export const coverUrl = (bookId: string) => `/api/books/${bookId}/cover`
export const downloadUrl = (jobId: string) => `/api/jobs/${jobId}/download`

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
