import { useEffect, useRef, useState } from 'react'
import confetti from 'canvas-confetti'
import { AlertCircle, ArrowLeft, BookPlus, Download, Loader2, Square } from 'lucide-react'

import { AidsToggle, ReaderSurface, SentencePair, type Aids } from '@/components/reader'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { type JobSnapshot, cancelJob, downloadUrl, formatDuration } from '@/lib/api'
import { cn } from '@/lib/utils'

type Props = {
  job: JobSnapshot
  bookTitle: string
  onBack: () => void
  onNewBook: () => void
}

const STAGES = [
  { key: 'preparing', label: 'Splitting sentences' },
  { key: 'translating', label: 'Translating with Claude' },
  { key: 'packaging', label: 'Adding pinyin & building EPUB' },
  { key: 'done', label: 'Ready' },
] as const

export function ConvertStep({ job, bookTitle, onBack, onNewBook }: Props) {
  const [aids, setAids] = useState<Aids>({ pinyin: true, english: true })
  const stageIndex = STAGES.findIndex((s) => s.key === job.stage)
  const pct =
    job.status === 'done'
      ? 100
      : job.stage === 'packaging'
        ? 96
        : job.total
          ? Math.max(3, Math.round((job.done / job.total) * 92))
          : 2

  const elapsed = useTicker(job.status === 'running', job.elapsed)
  const rate = job.done > 0 && elapsed > 0 ? job.done / elapsed : 0
  const remaining = rate > 0 ? (job.total - job.done) / rate : null

  if (job.status === 'error' || job.status === 'cancelled') {
    return (
      <div className="animate-in fade-in mx-auto max-w-2xl space-y-4 duration-300">
        <Alert variant={job.status === 'error' ? 'destructive' : 'default'}>
          <AlertCircle />
          <AlertTitle>{job.status === 'error' ? 'The conversion stopped' : 'Conversion cancelled'}</AlertTitle>
          <AlertDescription>{job.error || 'No EPUB was created.'}</AlertDescription>
        </Alert>
        <Button variant="outline" onClick={onBack} className="gap-1.5">
          <ArrowLeft /> Back to chapter selection
        </Button>
      </div>
    )
  }

  const pairs = [...job.preview].reverse().slice(0, 8)

  return (
    <div className="animate-in fade-in slide-in-from-bottom-3 space-y-6 duration-500">
      {job.status === 'done' ? (
        <DoneCard job={job} bookTitle={bookTitle} onBack={onBack} onNewBook={onNewBook} />
      ) : (
        <Card className="gap-5 px-6 py-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Creating your reader</p>
              <h2 className="text-xl font-semibold tracking-tight">{bookTitle}</h2>
            </div>
            <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => cancelJob(job.id)}>
              <Square className="size-3" /> Cancel
            </Button>
          </div>
          <div className="space-y-2">
            <Progress value={pct} className="h-2.5 transition-all" />
            <div className="flex justify-between text-sm text-muted-foreground tabular-nums">
              <span>
                {job.total > 0
                  ? `${job.done.toLocaleString()} of ${job.total.toLocaleString()} lines translated`
                  : 'Getting started…'}
              </span>
              <span>
                {formatDuration(elapsed)} elapsed
                {remaining !== null && job.stage === 'translating' && ` · ~${formatDuration(remaining)} left`}
              </span>
            </div>
          </div>
          <ol className="grid gap-2 sm:grid-cols-4">
            {STAGES.map((s, i) => (
              <li
                key={s.key}
                className={cn(
                  'flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition-colors',
                  i < stageIndex && 'border-primary/20 bg-primary/5 text-foreground',
                  i === stageIndex && 'border-primary/40 bg-accent font-medium',
                  i > stageIndex && 'text-muted-foreground',
                )}
              >
                {i === stageIndex ? (
                  <Loader2 className="size-3.5 animate-spin text-primary" />
                ) : (
                  <span
                    className={cn('size-1.5 rounded-full', i < stageIndex ? 'bg-primary' : 'bg-muted-foreground/40')}
                  />
                )}
                {s.label}
              </li>
            ))}
          </ol>
        </Card>
      )}

      <Card className="gap-0 overflow-hidden p-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-6 py-3">
          <div>
            <h3 className="font-medium">{job.status === 'done' ? 'A taste of your book' : 'Fresh off the press'}</h3>
            <p className="text-sm text-muted-foreground">
              Try reading the characters first — hide the aids and hover to peek.
            </p>
          </div>
          <AidsToggle aids={aids} onChange={setAids} />
        </div>
        <ReaderSurface aids={aids} className="paper-grain min-h-64 px-6 py-5 sm:px-10">
          {pairs.length === 0 ? (
            <div className="flex min-h-56 flex-col items-center justify-center gap-3 text-muted-foreground">
              <Loader2 className="size-6 animate-spin" />
              <p className="text-sm">The first sentences will appear here in a moment…</p>
            </div>
          ) : (
            <div className="space-y-5">
              {pairs.map((p) => (
                <SentencePair
                  key={p.id}
                  html={p.html}
                  en={p.en}
                  className="animate-in fade-in slide-in-from-top-2 duration-500"
                />
              ))}
            </div>
          )}
        </ReaderSurface>
      </Card>
    </div>
  )
}

function DoneCard({ job, bookTitle, onBack, onNewBook }: Props) {
  const fired = useRef(false)
  useEffect(() => {
    if (fired.current) return
    fired.current = true
    const colors = ['#c8402c', '#e0a43a', '#f4e3c3', '#8f2a1e']
    confetti({ particleCount: 90, spread: 75, origin: { y: 0.3 }, colors, disableForReducedMotion: true })
    setTimeout(
      () => confetti({ particleCount: 60, spread: 110, origin: { y: 0.25 }, colors, disableForReducedMotion: true }),
      250,
    )
  }, [])

  const s = job.stats
  const untranslated = (s.sentences ?? 0) - (s.translated ?? 0)

  return (
    <Card className="relative gap-6 overflow-hidden border-primary/25 px-6 py-8 text-center sm:px-10">
      <div className="paper-grain pointer-events-none absolute inset-0" />
      <div className="relative space-y-2">
        <div className="reader">
          <p className="zh !text-3xl !leading-[2.4]">
            <ruby>
              书<rt>shū</rt>
            </ruby>
            <ruby>
              做<rt>zuò</rt>
              好<rt>hǎo</rt>
            </ruby>
            <ruby>
              了<rt>le</rt>
            </ruby>
            ！
          </p>
        </div>
        <h2 className="text-2xl font-semibold tracking-tight">Your reader is ready</h2>
        <p className="text-muted-foreground">{bookTitle}</p>
      </div>

      <div className="relative mx-auto grid max-w-xl grid-cols-2 gap-3 sm:grid-cols-4">
        <BigStat value={s.sentences ?? 0} label="sentences" />
        <BigStat value={s.characters ?? 0} label="characters to read" />
        <BigStat value={s.unique_characters ?? 0} label="unique hanzi" />
        <BigStat value={s.chapters ?? 0} label={s.chapters === 1 ? 'chapter' : 'chapters'} />
      </div>

      <div className="relative flex flex-wrap items-center justify-center gap-3">
        <Button size="lg" asChild className="gap-2 px-6">
          <a href={downloadUrl(job.id)} download={job.filename}>
            <Download /> Download EPUB
            <span className="opacity-70">· {s.size_kb} KB</span>
          </a>
        </Button>
        <Button size="lg" variant="outline" onClick={onBack} className="gap-2">
          <BookPlus /> Convert more of this book
        </Button>
        <Button size="lg" variant="ghost" onClick={onNewBook}>
          New book
        </Button>
      </div>
      {untranslated > 0 && (
        <p className="relative text-xs text-muted-foreground">
          {untranslated} sentence{untranslated === 1 ? '' : 's'} couldn't be translated and appear in English only.
        </p>
      )}
      <p className="relative text-xs text-muted-foreground">
        Works in Apple Books, Google Play Books, Kobo, Calibre, KOReader — or send it to your Kindle.
      </p>
    </Card>
  )
}

function BigStat({ value, label }: { value: number; label: string }) {
  const shown = useCountUp(value)
  return (
    <div className="rounded-xl border bg-card/80 px-3 py-3">
      <div className="text-2xl font-semibold tabular-nums">{shown.toLocaleString()}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  )
}

function useCountUp(target: number, ms = 900) {
  const [value, setValue] = useState(0)
  useEffect(() => {
    let frame = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / ms)
      setValue(Math.round(target * (1 - Math.pow(1 - t, 3))))
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [target, ms])
  return value
}

/** Seconds since the job started, ticking locally between server updates. */
function useTicker(running: boolean, serverElapsed: number) {
  const [base, setBase] = useState({ server: serverElapsed, at: Date.now() })
  const [, force] = useState(0)
  useEffect(() => setBase({ server: serverElapsed, at: Date.now() }), [serverElapsed])
  useEffect(() => {
    if (!running) return
    const id = setInterval(() => force((n) => n + 1), 1000)
    return () => clearInterval(id)
  }, [running])
  return running ? base.server + (Date.now() - base.at) / 1000 : serverElapsed
}
