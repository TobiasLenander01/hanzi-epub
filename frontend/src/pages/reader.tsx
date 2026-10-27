import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, BookPlus, ChevronLeft, List, Loader2, Minus, Plus, Type } from 'lucide-react'

import { ThemeToggle } from '@/components/chrome'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { type BookMeta, type ChapterData, type ChapterSummary, getBookMeta, getChapter } from '@/lib/api'
import { href, navigate } from '@/lib/router'
import { TEXT_SIZES, progressStore, readerSettings, saveProgress, useTheme } from '@/lib/store'
import { cn } from '@/lib/utils'

export function ReaderPage({ bookId, chapterKey }: { bookId: string; chapterKey: number | null }) {
  const [meta, setMeta] = useState<BookMeta | null>(null)
  const [chapter, setChapter] = useState<ChapterData | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    getBookMeta(bookId).then(setMeta, (e) => setError((e as Error).message))
  }, [bookId])

  // No chapter in the URL: resume where the reader left off, or start at the beginning.
  const saved = progressStore.get()[bookId]
  const key =
    chapterKey ??
    (meta ? (meta.chapters.some((c) => c.key === saved?.key) ? saved!.key : meta.chapters[0]?.key) : undefined)

  useEffect(() => {
    if (key === undefined) return
    let alive = true
    setChapter(null)
    getChapter(bookId, key).then(
      (c) => alive && setChapter(c),
      (e) => alive && setError((e as Error).message),
    )
    return () => {
      alive = false
    }
  }, [bookId, key])

  if (error) {
    return (
      <div className="flex min-h-svh flex-col items-center justify-center gap-4 p-6 text-center">
        <p className="text-muted-foreground">{error}</p>
        <Button asChild variant="outline">
          <a href={href.library()}>Back to library</a>
        </Button>
      </div>
    )
  }
  if (!meta || key === undefined) return <FullPageSpinner />

  return <Reader meta={meta} chapterKey={key} chapter={chapter} />
}

function FullPageSpinner() {
  return (
    <div className="flex min-h-svh items-center justify-center">
      <Loader2 className="size-6 animate-spin text-muted-foreground" />
    </div>
  )
}

function Reader({ meta, chapterKey, chapter }: { meta: BookMeta; chapterKey: number; chapter: ChapterData | null }) {
  const settings = readerSettings.use()
  const index = meta.chapters.findIndex((c) => c.key === chapterKey)
  const prev = meta.chapters[index - 1]
  const next = meta.chapters[index + 1]
  const summary = meta.chapters[index]
  const [barHidden, setBarHidden] = useState(false)
  const mainRef = useRef<HTMLElement>(null)
  const progressRef = useRef<HTMLDivElement>(null)

  // Restore the reading position once the chapter is on screen. Positions are saved as a
  // paragraph index rather than a scroll offset: off-screen paragraphs aren't laid out
  // (content-visibility), so the page height is partly an estimate.
  useLayoutEffect(() => {
    if (!chapter) return
    const blocks = mainRef.current?.querySelectorAll<HTMLElement>('[data-block]') ?? []
    const saved = progressStore.get()[meta.id]
    const block = saved?.key === chapter.key ? (saved.block ?? Math.round(saved.fraction * blocks.length)) : 0
    if (block > 0 && blocks[block]) blocks[block].scrollIntoView({ block: 'start' })
    else window.scrollTo({ top: 0 })
    saveProgress(meta.id, chapter.key, block, blocks.length)
  }, [chapter, meta.id])

  // Track reading position, and tuck the top bar away while scrolling down. This runs at most
  // once per frame and touches the DOM directly, so scrolling never re-renders the chapter.
  useEffect(() => {
    if (!chapter) return
    const blocks = [...(mainRef.current?.querySelectorAll<HTMLElement>('[data-block]') ?? [])]
    let lastY = window.scrollY
    let hidden = false
    let frame = 0
    let timer = 0
    const update = () => {
      frame = 0
      const y = window.scrollY
      const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight)
      progressRef.current?.style.setProperty('transform', `scaleX(${Math.min(1, y / max)})`)
      if (Math.abs(y - lastY) > 6) {
        const hide = y > lastY && y > 120
        if (hide !== hidden) setBarHidden((hidden = hide))
        lastY = y
      }
      window.clearTimeout(timer)
      timer = window.setTimeout(() => saveProgress(meta.id, chapter.key, firstVisible(blocks), blocks.length), 300)
    }
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(update)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(frame)
      window.clearTimeout(timer)
    }
  }, [chapter, meta.id])

  // ← / → move between chapters.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.metaKey || e.ctrlKey || e.altKey) return
      if (e.key === 'ArrowRight' && next) navigate(href.read(meta.id, next.key))
      if (e.key === 'ArrowLeft' && prev) navigate(href.read(meta.id, prev.key))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [meta.id, next, prev])

  // With an aid hidden, tapping a sentence reveals it for that sentence only.
  const onTap = (e: React.MouseEvent) => {
    if (settings.pinyin && settings.english) return
    const pair = (e.target as HTMLElement).closest('.pair')
    pair?.classList.toggle('revealed')
  }

  return (
    <div className="min-h-svh">
      <header
        className={cn(
          'sticky top-0 z-30 border-b bg-background/85 backdrop-blur transition-transform duration-300',
          barHidden && '-translate-y-full',
        )}
      >
        <div className="mx-auto flex h-14 max-w-4xl items-center gap-1 px-2 sm:px-4">
          <Button asChild variant="ghost" size="icon" aria-label="Back to library">
            <a href={href.library()}>
              <ChevronLeft />
            </a>
          </Button>
          <div className="min-w-0 flex-1 px-1 leading-tight">
            <p className="truncate font-[family-name:var(--font-hanzi)] text-sm font-semibold">
              {meta.title_zh || meta.title}
            </p>
            <p className="truncate text-xs text-muted-foreground">
              {summary ? `${summary.title_zh || summary.title_en} · ${summary.title_en}` : meta.title}
            </p>
          </div>
          <Contents meta={meta} current={chapterKey} />
          <SettingsPopover />
          <ThemeToggle />
        </div>
        <div className="absolute inset-x-0 -bottom-px h-0.5">
          <div ref={progressRef} className="h-full origin-left bg-primary" style={{ transform: 'scaleX(0)' }} />
        </div>
      </header>

      <main
        ref={mainRef}
        onClick={onTap}
        className={cn(
          'reader reader-page mx-auto max-w-[42rem] px-5 pt-10 pb-16 sm:px-8 sm:pt-16',
          !settings.pinyin && 'hide-pinyin',
          !settings.english && 'hide-english',
        )}
        style={{ '--reader-scale': TEXT_SIZES[settings.size] ?? 1 } as React.CSSProperties}
      >
        {!chapter ? (
          <ChapterSkeleton />
        ) : (
          <article key={chapter.key} className="animate-in fade-in duration-300">
            <ChapterHeader chapter={chapter} />
            <ChapterBody chapter={chapter} />
            <ChapterFooter meta={meta} chapter={chapter} prev={prev} next={next} />
          </article>
        )}
      </main>
    </div>
  )
}

/** Index of the first block whose bottom edge is below the top bar. */
function firstVisible(blocks: HTMLElement[]): number {
  let lo = 0
  let hi = blocks.length - 1
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (blocks[mid].getBoundingClientRect().bottom > 72) hi = mid
    else lo = mid + 1
  }
  return Math.max(0, lo)
}

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')

/** A part title ("PART ONE: …") that opens the chapter body belongs above the chapter title. */
function splitPartHeading(chapter: ChapterData) {
  const first = chapter.body[0]
  if (first?.kind === 'heading' && chapter.part && norm(first.en) === norm(chapter.part)) {
    return { partHeading: first, body: chapter.body.slice(1) }
  }
  return { partHeading: null, body: chapter.body }
}

const ChapterHeader = memo(function ChapterHeader({ chapter }: { chapter: ChapterData }) {
  const { partHeading } = splitPartHeading(chapter)
  return (
    <header className="mb-12 sm:mb-16">
      {partHeading ? (
        <div className="part-heading mb-6">
          {partHeading.zh && <p className="zh" dangerouslySetInnerHTML={{ __html: partHeading.html }} />}
          <p className="en">{partHeading.en}</p>
        </div>
      ) : (
        chapter.part && (
          <p className="mb-4 text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">{chapter.part}</p>
        )
      )}
      {chapter.title_zh && <h1 className="zh chapter-title" dangerouslySetInnerHTML={{ __html: chapter.title_html }} />}
      <p className="en chapter-subtitle">{chapter.title_en}</p>
    </header>
  )
})

// Memoized: a chapter is tens of thousands of elements, and nothing about it changes while reading.
const ChapterBody = memo(function ChapterBody({ chapter }: { chapter: ChapterData }) {
  const { body } = splitPartHeading(chapter)
  return (
    <div className="space-y-[1.9em]">
      {body.map((block, i) =>
        block.kind === 'heading' ? (
          <div key={i} data-block={i} className="pair subhead">
            {block.zh && <h2 className="zh" dangerouslySetInnerHTML={{ __html: block.html }} />}
            <p className="en">{block.en}</p>
          </div>
        ) : (
          <div key={i} data-block={i} className="para">
            {block.pairs.map((p, j) =>
              p.zh ? (
                <div key={j} className="pair">
                  <p className="zh" dangerouslySetInnerHTML={{ __html: p.html }} />
                  <p className="en">{p.en}</p>
                </div>
              ) : (
                <div key={j} className="pair untranslated">
                  <p className="en">{p.en}</p>
                </div>
              ),
            )}
          </div>
        ),
      )}
    </div>
  )
})

function ChapterFooter({
  meta,
  chapter,
  prev,
  next,
}: {
  meta: BookMeta
  chapter: ChapterData
  prev?: ChapterSummary
  next?: ChapterSummary
}) {
  const moreToTranslate = meta.chapters.length < meta.source_chapters || chapter.partial
  return (
    <footer className="mt-20 space-y-6 border-t pt-8 font-sans">
      {chapter.partial && (
        <p className="text-center text-sm text-muted-foreground">
          Only part of this chapter has been translated.
        </p>
      )}
      <nav className="grid gap-3 sm:grid-cols-2">
        {prev ? (
          <ChapterLink bookId={meta.id} chapter={prev} direction="prev" />
        ) : (
          <span className="hidden sm:block" />
        )}
        {next ? (
          <ChapterLink bookId={meta.id} chapter={next} direction="next" />
        ) : (
          <div className="rounded-xl border border-dashed p-4 text-center sm:col-start-2">
            <p className="font-medium">{moreToTranslate ? 'That’s all that’s translated so far' : '全书完 · The end'}</p>
            <div className="mt-3 flex flex-wrap justify-center gap-2">
              {moreToTranslate && (
                <Button asChild size="sm" className="gap-1.5">
                  <a href={href.add(meta.id)}>
                    <BookPlus /> Translate more
                  </a>
                </Button>
              )}
              <Button asChild size="sm" variant="outline">
                <a href={href.library()}>Back to library</a>
              </Button>
            </div>
          </div>
        )}
      </nav>
    </footer>
  )
}

function ChapterLink({
  bookId,
  chapter,
  direction,
}: {
  bookId: string
  chapter: ChapterSummary
  direction: 'prev' | 'next'
}) {
  return (
    <a
      href={href.read(bookId, chapter.key)}
      className={cn(
        'group flex items-center gap-3 rounded-xl border bg-card p-4 transition-colors hover:border-primary/40 hover:bg-accent/40',
        direction === 'next' && 'flex-row-reverse text-right sm:col-start-2',
      )}
    >
      {direction === 'prev' ? (
        <ArrowLeft className="size-4 shrink-0 text-muted-foreground transition-transform group-hover:-translate-x-0.5" />
      ) : (
        <ArrowRight className="size-4 shrink-0 text-primary transition-transform group-hover:translate-x-0.5" />
      )}
      <span className="min-w-0">
        <span className="block text-xs text-muted-foreground">{direction === 'prev' ? 'Previous' : 'Next chapter'}</span>
        <span className="block truncate font-[family-name:var(--font-hanzi)] font-semibold">
          {chapter.title_zh || chapter.title_en}
        </span>
        <span className="block truncate text-sm text-muted-foreground">{chapter.title_en}</span>
      </span>
    </a>
  )
}

function Contents({ meta, current }: { meta: BookMeta; current: number }) {
  const [open, setOpen] = useState(false)
  const groups = useMemo(() => {
    const out: { part: string; chapters: ChapterSummary[] }[] = []
    for (const c of meta.chapters) {
      const last = out.at(-1)
      if (last && last.part === c.part) last.chapters.push(c)
      else out.push({ part: c.part, chapters: [c] })
    }
    return out
  }, [meta.chapters])

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Contents">
          <List />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="w-[min(22rem,88vw)] gap-0 p-0">
        <SheetHeader className="border-b">
          <SheetTitle className="font-[family-name:var(--font-hanzi)] text-lg">{meta.title_zh || meta.title}</SheetTitle>
          <SheetDescription>
            {meta.title} · {meta.chapters.length}
            {meta.chapters.length < meta.source_chapters && ` of ${meta.source_chapters}`} chapters
          </SheetDescription>
        </SheetHeader>
        <nav className="flex-1 overflow-y-auto py-2">
          {groups.map((g, gi) => (
            <div key={gi} className="py-1">
              {g.part && (
                <p className="px-4 pt-3 pb-1 text-[0.7rem] font-semibold tracking-wider text-muted-foreground uppercase">
                  {g.part}
                </p>
              )}
              {g.chapters.map((c) => (
                <a
                  key={c.key}
                  href={href.read(meta.id, c.key)}
                  onClick={() => setOpen(false)}
                  className={cn(
                    'flex items-baseline gap-3 px-4 py-2 transition-colors hover:bg-accent/60',
                    c.key === current && 'bg-accent text-accent-foreground',
                  )}
                >
                  <span className="shrink-0 font-[family-name:var(--font-hanzi)] font-medium">
                    {c.title_zh || c.title_en}
                  </span>
                  <span className="truncate text-sm text-muted-foreground">{c.title_en}</span>
                  {c.key === current && <span className="ml-auto size-1.5 shrink-0 rounded-full bg-primary" />}
                </a>
              ))}
            </div>
          ))}
        </nav>
        {meta.chapters.length < meta.source_chapters && (
          <div className="border-t p-4">
            <Button asChild variant="outline" className="w-full gap-1.5">
              <a href={href.add(meta.id)}>
                <BookPlus /> Translate more chapters
              </a>
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

function SettingsPopover() {
  const settings = readerSettings.use()
  const [theme, setTheme] = useTheme()
  const set = (patch: Partial<typeof settings>) => readerSettings.set((s) => ({ ...s, ...patch }))
  const aids = [settings.pinyin && 'pinyin', settings.english && 'english'].filter(Boolean) as string[]

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Reading settings">
          <Type />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 space-y-5">
        <Setting label="Text size">
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon-sm"
              onClick={() => set({ size: Math.max(0, settings.size - 1) })}
              disabled={settings.size === 0}
              aria-label="Smaller text"
            >
              <Minus />
            </Button>
            <div className="flex flex-1 justify-center gap-1.5">
              {TEXT_SIZES.map((_, i) => (
                <span
                  key={i}
                  className={cn('size-1.5 rounded-full', i <= settings.size ? 'bg-primary' : 'bg-muted-foreground/25')}
                />
              ))}
            </div>
            <Button
              variant="outline"
              size="icon-sm"
              onClick={() => set({ size: Math.min(TEXT_SIZES.length - 1, settings.size + 1) })}
              disabled={settings.size === TEXT_SIZES.length - 1}
              aria-label="Larger text"
            >
              <Plus />
            </Button>
          </div>
        </Setting>
        <Setting label="Reading aids" hint={aids.length < 2 ? 'Tap a sentence to reveal what’s hidden.' : undefined}>
          <ToggleGroup
            type="multiple"
            variant="outline"
            size="sm"
            value={aids}
            onValueChange={(v) => set({ pinyin: v.includes('pinyin'), english: v.includes('english') })}
            className="w-full"
          >
            <ToggleGroupItem value="pinyin" className="flex-1">
              Pinyin
            </ToggleGroupItem>
            <ToggleGroupItem value="english" className="flex-1">
              English
            </ToggleGroupItem>
          </ToggleGroup>
        </Setting>
        <Setting label="Theme">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={theme}
            onValueChange={(v) => v && setTheme(v as typeof theme)}
            className="w-full"
          >
            <ToggleGroupItem value="light" className="flex-1">
              Light
            </ToggleGroupItem>
            <ToggleGroupItem value="dark" className="flex-1">
              Dark
            </ToggleGroupItem>
          </ToggleGroup>
        </Setting>
      </PopoverContent>
    </Popover>
  )
}

function Setting({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{label}</p>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  )
}

function ChapterSkeleton() {
  return (
    <div className="animate-pulse space-y-10">
      <div className="h-12 w-40 rounded-md bg-muted" />
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="space-y-3">
          <div className="h-8 w-full rounded-md bg-muted" />
          <div className="h-8 w-4/5 rounded-md bg-muted" />
          <div className="h-4 w-3/4 rounded bg-muted/70" />
        </div>
      ))}
    </div>
  )
}
