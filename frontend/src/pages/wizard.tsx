import { useEffect, useRef, useState } from 'react'
import { KeyRound, Loader2, X } from 'lucide-react'
import { toast } from 'sonner'

import { ThemeToggle, TopBar } from '@/components/chrome'
import { ConvertStep } from '@/components/convert-step'
import { Dropzone } from '@/components/dropzone'
import { AidsToggle, ReaderSurface, SAMPLE, SentencePair, type Aids } from '@/components/reader'
import { SelectionStep } from '@/components/selection-step'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  type BookInfo,
  type Health,
  type JobSnapshot,
  type Script,
  type Selection,
  getHealth,
  openSource,
  startConversion,
  uploadBook,
  watchJob,
} from '@/lib/api'
import { href } from '@/lib/router'
import { cn } from '@/lib/utils'

type Step = 'upload' | 'select' | 'convert'

export function WizardPage({ libraryId }: { libraryId: string | null }) {
  const [health, setHealth] = useState<Health | null>(null)
  const [book, setBook] = useState<BookInfo | null>(null)
  const [job, setJob] = useState<JobSnapshot | null>(null)
  const [uploading, setUploading] = useState(!!libraryId)
  const [starting, setStarting] = useState(false)
  const stopWatching = useRef<(() => void) | null>(null)

  const step: Step = job ? 'convert' : book ? 'select' : 'upload'

  useEffect(() => {
    let alive = true
    const check = () =>
      getHealth()
        .then((h) => alive && setHealth(h))
        .catch(
          () =>
            alive &&
            setHealth({
              ok: false,
              model: '',
              api_ready: false,
              api_message: "The backend server isn't running. Start it with: uvicorn app.main:app --port 8000",
            }),
        )
    check()
    const id = setInterval(() => health?.api_ready || check(), 15000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [health?.api_ready])

  // "Translate more chapters" from the library: reopen the book's original EPUB.
  useEffect(() => {
    if (!libraryId) return
    setUploading(true)
    openSource(libraryId)
      .then(setBook)
      .catch((e) => toast.error((e as Error).message))
      .finally(() => setUploading(false))
  }, [libraryId])

  useEffect(() => () => stopWatching.current?.(), [])

  // Chapters saved by a conversion count as translated when choosing what to do next.
  const scriptRef = useRef<Script>('simplified')
  const saved = job?.saved
  useEffect(() => {
    if (!saved?.length) return
    const script = scriptRef.current
    setBook((b) => b && { ...b, translated: { ...b.translated, [script]: [...new Set([...b.translated[script], ...saved])] } })
  }, [saved?.length]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.epub')) {
      toast.error('Please choose an .epub file.')
      return
    }
    setUploading(true)
    try {
      setBook(await uploadBook(file))
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setUploading(false)
    }
  }

  const handleConvert = async (selection: Selection, script: Script) => {
    if (!book) return
    setStarting(true)
    scriptRef.current = script
    try {
      const jobId = await startConversion(book.id, selection, script)
      stopWatching.current?.()
      setJob({
        id: jobId,
        status: 'running',
        stage: 'preparing',
        total: 0,
        done: 0,
        error: '',
        library_id: '',
        saved: [],
        preview: [],
        stats: {},
        elapsed: 0,
      })
      stopWatching.current = watchJob(jobId, setJob)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setStarting(false)
    }
  }

  const backToSelection = () => {
    stopWatching.current?.()
    setJob(null)
  }

  const reset = () => {
    backToSelection()
    setBook(null)
  }

  return (
    <div className="min-h-svh">
      <TopBar>
        <Button asChild variant="ghost" size="icon" aria-label="Back to library">
          <a href={href.library()}>
            <X />
          </a>
        </Button>
        <span className="font-semibold tracking-tight">Add a book</span>
        <Steps step={step} />
        <div className="ml-auto sm:ml-2">
          <ThemeToggle />
        </div>
      </TopBar>

      <main className="mx-auto max-w-5xl space-y-6 px-4 py-8 sm:px-6 sm:py-10">
        {health && !health.api_ready && (
          <Alert>
            <KeyRound />
            <AlertTitle>Connect Claude to start translating</AlertTitle>
            <AlertDescription>
              <p>{health.api_message}</p>
              <p>
                Copy <code className="rounded bg-muted px-1">backend/.env.example</code> to{' '}
                <code className="rounded bg-muted px-1">backend/.env</code>, add your key, then restart the backend.
                You can still upload a book and pick chapters meanwhile.
              </p>
            </AlertDescription>
          </Alert>
        )}

        {step === 'upload' &&
          (libraryId ? (
            <div className="flex min-h-64 items-center justify-center">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <UploadStep uploading={uploading} onFile={handleFile} />
          ))}
        {step === 'select' && book && (
          <SelectionStep
            book={book}
            apiReady={!!health?.api_ready}
            starting={starting}
            onConvert={handleConvert}
            onReset={libraryId ? undefined : reset}
          />
        )}
        {step === 'convert' && job && book && (
          <ConvertStep job={job} bookTitle={book.title} onBack={backToSelection} />
        )}
      </main>
    </div>
  )
}

function Steps({ step }: { step: Step }) {
  const steps: [Step, string][] = [
    ['upload', 'Upload'],
    ['select', 'Choose'],
    ['convert', 'Translate'],
  ]
  const current = steps.findIndex(([s]) => s === step)
  return (
    <ol className="ml-auto hidden items-center gap-1 text-sm sm:flex">
      {steps.map(([key, label], i) => (
        <li key={key} className="flex items-center gap-1">
          {i > 0 && <span className={cn('h-px w-6 bg-border', i <= current && 'bg-primary/50')} />}
          <span
            className={cn(
              'flex items-center gap-1.5 rounded-full px-2.5 py-1 transition-colors',
              i === current ? 'bg-accent font-medium text-accent-foreground' : 'text-muted-foreground',
            )}
          >
            <span
              className={cn(
                'flex size-5 items-center justify-center rounded-full text-xs',
                i <= current ? 'bg-primary text-primary-foreground' : 'bg-muted',
              )}
            >
              {i + 1}
            </span>
            {label}
          </span>
        </li>
      ))}
    </ol>
  )
}

function UploadStep({ uploading, onFile }: { uploading: boolean; onFile: (f: File) => void }) {
  const [aids, setAids] = useState<Aids>({ pinyin: true, english: true })
  return (
    <div className="animate-in fade-in slide-in-from-bottom-3 grid items-center gap-10 duration-500 lg:grid-cols-[1.05fr_1fr]">
      <div className="space-y-6">
        <div className="space-y-4">
          <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs text-muted-foreground">
            <span className="size-1.5 rounded-full bg-primary" /> 汉英对照 · bilingual graded reading
          </p>
          <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
            Learn to read hanzi with books you actually want to read.
          </h1>
          <p className="text-lg text-pretty text-muted-foreground">
            Upload an English EPUB, pick the chapters, and they join your library as natural Mandarin — pinyin
            floating quietly above, the original English softly below.
          </p>
        </div>
        <Dropzone onFile={onFile} busy={uploading} />
      </div>

      <Card className="gap-0 overflow-hidden p-0 shadow-xl shadow-primary/5">
        <div className="flex items-center justify-between gap-3 border-b px-5 py-3">
          <span className="text-sm text-muted-foreground">What a page looks like</span>
          <AidsToggle aids={aids} onChange={setAids} />
        </div>
        <ReaderSurface aids={aids} className="paper-grain space-y-6 px-6 py-8 sm:px-8">
          {SAMPLE.map((s, i) => (
            <SentencePair key={i} html={s.html} en={s.en} />
          ))}
          <ul className="space-y-1.5 border-t pt-5 text-sm text-muted-foreground">
            <li>
              <span className="font-medium text-foreground">Hanzi</span> large and dark — read these first
            </li>
            <li>
              <span className="font-medium text-foreground">Pinyin</span> small and grey, word-aware tones from
              jieba + pypinyin
            </li>
            <li>
              <span className="font-medium text-foreground">English</span> underneath, to check yourself
            </li>
          </ul>
        </ReaderSurface>
      </Card>
    </div>
  )
}
