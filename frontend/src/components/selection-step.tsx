import { useMemo, useRef, useState } from 'react'
import { BookOpen, Check, Clock, Coins, FileText, Languages, ListChecks, Minus, Sparkles, X } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Slider } from '@/components/ui/slider'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import {
  type BookInfo,
  type Chapter,
  type Script,
  type Selection,
  coverUrl,
  estimate,
  formatCost,
  formatDuration,
} from '@/lib/api'
import { cn } from '@/lib/utils'

const TINY = 40 // words: title pages, colophons and the like

type Props = {
  book: BookInfo
  apiReady: boolean
  starting: boolean
  onConvert: (selection: Selection, script: Script) => void
  onReset: () => void
}

export function SelectionStep({ book, apiReady, starting, onConvert, onReset }: Props) {
  const [mode, setMode] = useState<'chapters' | 'pages'>('chapters')
  const [selected, setSelected] = useState<Set<number>>(() => {
    const first = book.chapters.find((c) => c.word_count >= 300) ?? book.chapters[0]
    return new Set([first.index])
  })
  const [range, setRange] = useState<[number, number]>(() => {
    const first = book.chapters.find((c) => c.word_count >= 300) ?? book.chapters[0]
    return [first.start_page, Math.min(first.start_page + 9, book.total_pages)]
  })
  const [script, setScript] = useState<Script>('simplified')

  const words = useMemo(() => {
    if (mode === 'chapters') {
      return book.chapters.filter((c) => selected.has(c.index)).reduce((n, c) => n + c.word_count, 0)
    }
    return Math.min(book.word_count, (range[1] - range[0] + 1) * book.words_per_page)
  }, [mode, selected, range, book])

  const est = estimate(words)
  const empty = mode === 'chapters' ? selected.size === 0 : false
  const selection: Selection =
    mode === 'chapters'
      ? { mode, chapters: [...selected].sort((a, b) => a - b) }
      : { mode, page_start: range[0], page_end: range[1] }

  return (
    <div className="animate-in fade-in slide-in-from-bottom-3 space-y-6 duration-500">
      <BookHeader book={book} onReset={onReset} />

      <Card className="gap-0 overflow-hidden p-0">
        <Tabs value={mode} onValueChange={(v) => setMode(v as typeof mode)} className="gap-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
            <div>
              <h2 className="font-medium">What would you like to read?</h2>
              <p className="text-sm text-muted-foreground">Start small — a chapter is a great first session.</p>
            </div>
            <TabsList>
              <TabsTrigger value="chapters" className="gap-1.5">
                <ListChecks /> Chapters
              </TabsTrigger>
              <TabsTrigger value="pages" className="gap-1.5">
                <FileText /> Page range
              </TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="chapters" className="m-0">
            <ChapterList chapters={book.chapters} selected={selected} onChange={setSelected} />
          </TabsContent>
          <TabsContent value="pages" className="m-0">
            <PageRange book={book} range={range} onChange={setRange} />
          </TabsContent>
        </Tabs>
      </Card>

      <div className="sticky bottom-4 z-10">
        <Card className="flex-row flex-wrap items-center gap-x-6 gap-y-4 border-primary/20 px-5 py-4 shadow-lg shadow-primary/5 backdrop-blur supports-backdrop-filter:bg-card/90">
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm">
            <Stat icon={<BookOpen />} label={`${words.toLocaleString()} words`} />
            <Stat icon={<Languages />} label={`≈ ${est.sentences.toLocaleString()} sentences`} />
            <Stat icon={<Clock />} label={`≈ ${formatDuration(est.seconds)}`} hint="Rough translation time" />
            <Stat icon={<Coins />} label={formatCost(est.cost)} hint="Estimated Claude Haiku 5.5 API cost" />
          </div>
          <div className="ml-auto flex items-center gap-3">
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={script}
              onValueChange={(v) => v && setScript(v as Script)}
              aria-label="Character set"
            >
              <ToggleGroupItem value="simplified" className="px-3 font-[family-name:var(--font-hanzi)]">
                简体
              </ToggleGroupItem>
              <ToggleGroupItem value="traditional" className="px-3 font-[family-name:var(--font-hanzi)]">
                繁體
              </ToggleGroupItem>
            </ToggleGroup>
            <Button
              size="lg"
              disabled={empty || !apiReady || starting || words === 0}
              onClick={() => onConvert(selection, script)}
              className="gap-2 px-5"
            >
              <Sparkles />
              {starting ? 'Starting…' : 'Create my reader'}
            </Button>
          </div>
        </Card>
      </div>
    </div>
  )
}

function Stat({ icon, label, hint }: { icon: React.ReactNode; label: string; hint?: string }) {
  const body = (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground tabular-nums [&_svg]:size-3.5">
      {icon}
      <span className="text-foreground">{label}</span>
    </span>
  )
  if (!hint) return body
  return (
    <Tooltip>
      <TooltipTrigger asChild>{body}</TooltipTrigger>
      <TooltipContent>{hint}</TooltipContent>
    </Tooltip>
  )
}

function BookHeader({ book, onReset }: { book: BookInfo; onReset: () => void }) {
  return (
    <div className="flex items-center gap-5">
      <div className="flex h-28 w-20 shrink-0 items-center justify-center overflow-hidden rounded-md border bg-gradient-to-br from-primary/80 to-primary text-primary-foreground shadow-md">
        {book.has_cover ? (
          <img src={coverUrl(book.id)} alt="" className="size-full object-cover" />
        ) : (
          <span className="font-[family-name:var(--font-hanzi)] text-3xl">书</span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-2xl font-semibold tracking-tight">{book.title}</h1>
        {book.author && <p className="truncate text-muted-foreground">{book.author}</p>}
        <div className="mt-2 flex flex-wrap gap-2">
          <Badge variant="secondary">{book.chapters.length} sections</Badge>
          <Badge variant="secondary">{book.total_pages.toLocaleString()} pages</Badge>
          <Badge variant="secondary">{book.word_count.toLocaleString()} words</Badge>
        </div>
      </div>
      <Button variant="ghost" size="sm" onClick={onReset} className="shrink-0 gap-1.5 self-start">
        <X /> Different book
      </Button>
    </div>
  )
}

type Group = { part: string; chapters: Chapter[] }

function groupByPart(chapters: Chapter[]): Group[] {
  const groups: Group[] = []
  for (const c of chapters) {
    const last = groups.at(-1)
    if (last && last.part === c.part) last.chapters.push(c)
    else groups.push({ part: c.part, chapters: [c] })
  }
  return groups
}

function ChapterList({
  chapters,
  selected,
  onChange,
}: {
  chapters: Chapter[]
  selected: Set<number>
  onChange: (s: Set<number>) => void
}) {
  const anchor = useRef<number | null>(null)
  const groups = useMemo(() => groupByPart(chapters), [chapters])

  const toggle = (index: number, shift: boolean) => {
    const next = new Set(selected)
    if (shift && anchor.current !== null) {
      const [lo, hi] = [Math.min(anchor.current, index), Math.max(anchor.current, index)]
      const on = !selected.has(index)
      for (let i = lo; i <= hi; i++) on ? next.add(i) : next.delete(i)
    } else {
      next.has(index) ? next.delete(index) : next.add(index)
    }
    anchor.current = index
    onChange(next)
  }

  const setGroup = (group: Group, on: boolean) => {
    const next = new Set(selected)
    for (const c of group.chapters) on ? next.add(c.index) : next.delete(c.index)
    onChange(next)
  }

  const real = chapters.filter((c) => c.word_count >= TINY)

  return (
    <div>
      <div className="flex items-center justify-between gap-2 border-b bg-muted/40 px-5 py-2 text-sm">
        <span className="text-muted-foreground">
          {selected.size} of {chapters.length} selected
          <span className="hidden sm:inline"> · shift-click to select a range</span>
        </span>
        <div className="flex gap-1">
          <Button variant="ghost" size="xs" onClick={() => onChange(new Set(real.map((c) => c.index)))}>
            Select all
          </Button>
          <Button variant="ghost" size="xs" onClick={() => onChange(new Set())}>
            Clear
          </Button>
        </div>
      </div>
      <div className="max-h-[28rem] overflow-y-auto overscroll-contain">
        {groups.map((group, gi) => {
          const count = group.chapters.filter((c) => selected.has(c.index)).length
          return (
            <div key={gi}>
              {group.part && (
                <button
                  type="button"
                  onClick={() => setGroup(group, count < group.chapters.length)}
                  className="sticky top-0 z-[1] flex w-full items-center gap-3 border-b bg-card/95 px-5 py-2 text-left text-xs font-semibold tracking-wide text-muted-foreground uppercase backdrop-blur hover:text-foreground"
                >
                  <Tick state={count === 0 ? 'off' : count === group.chapters.length ? 'on' : 'some'} />
                  <span className="truncate">{group.part}</span>
                </button>
              )}
              {group.chapters.map((c) => (
                <ChapterRow key={c.index} chapter={c} checked={selected.has(c.index)} onToggle={toggle} />
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

function Tick({ state }: { state: 'on' | 'off' | 'some' }) {
  return (
    <span
      aria-hidden
      className={cn(
        'flex size-4 shrink-0 items-center justify-center rounded-[4px] border transition-colors',
        state === 'off' ? 'border-input bg-background' : 'border-primary bg-primary text-primary-foreground',
      )}
    >
      {state === 'on' && <Check className="size-3" strokeWidth={3} />}
      {state === 'some' && <Minus className="size-3" strokeWidth={3} />}
    </span>
  )
}

function ChapterRow({
  chapter: c,
  checked,
  onToggle,
}: {
  chapter: Chapter
  checked: boolean
  onToggle: (index: number, shift: boolean) => void
}) {
  const tiny = c.word_count < TINY
  return (
    <div
      role="checkbox"
      aria-checked={checked}
      tabIndex={0}
      onClick={(e) => onToggle(c.index, e.shiftKey)}
      onKeyDown={(e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault()
          onToggle(c.index, e.shiftKey)
        }
      }}
      className={cn(
        'flex cursor-pointer items-start gap-3 border-b border-border/60 px-5 py-3 transition-colors outline-none select-none last:border-b-0',
        'hover:bg-accent/40 focus-visible:bg-accent/50',
        checked && 'bg-accent/60 hover:bg-accent/70',
        tiny && !checked && 'opacity-55',
      )}
    >
      <span className="mt-0.5">
        <Tick state={checked ? 'on' : 'off'} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <span className="truncate font-medium">{c.title}</span>
          <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
            {tiny ? 'front matter' : `${c.word_count.toLocaleString()} words`}
            <span className="hidden sm:inline">
              {' '}
              · p. {c.start_page}
              {c.end_page > c.start_page && `–${c.end_page}`}
            </span>
          </span>
        </div>
        {!tiny && <p className="mt-0.5 line-clamp-1 text-sm text-muted-foreground">{c.preview}</p>}
      </div>
    </div>
  )
}

function PageRange({
  book,
  range,
  onChange,
}: {
  book: BookInfo
  range: [number, number]
  onChange: (r: [number, number]) => void
}) {
  const max = book.total_pages
  const covered = book.chapters.filter(
    (c) => c.word_count >= TINY && c.end_page >= range[0] && c.start_page <= range[1],
  )
  const clamp = (n: number) => Math.min(max, Math.max(1, Math.round(n) || 1))
  const presets: [string, [number, number]][] = [
    ['First 5 pages', [1, Math.min(5, max)]],
    ['First 20 pages', [1, Math.min(20, max)]],
    ['Next 10 pages', [Math.min(range[1] + 1, max), Math.min(range[1] + 10, max)]],
  ]

  return (
    <div className="space-y-6 px-5 py-6">
      <div className="flex flex-wrap items-end gap-4">
        <PageInput label="From page" value={range[0]} onChange={(v) => onChange([clamp(v), Math.max(clamp(v), range[1])])} />
        <PageInput label="To page" value={range[1]} onChange={(v) => onChange([Math.min(range[0], clamp(v)), clamp(v)])} />
        <p className="pb-2 text-sm text-muted-foreground">
          of {max.toLocaleString()} · {range[1] - range[0] + 1} page{range[1] === range[0] ? '' : 's'}
        </p>
        <div className="ml-auto flex flex-wrap gap-1.5 pb-1">
          {presets.map(([label, r]) => (
            <Button key={label} variant="outline" size="xs" onClick={() => onChange(r)}>
              {label}
            </Button>
          ))}
        </div>
      </div>
      <Slider
        min={1}
        max={max}
        step={1}
        value={range}
        onValueChange={(v) => onChange([v[0], v[1]] as [number, number])}
        className="py-2"
      />
      <div className="rounded-lg bg-muted/50 px-4 py-3 text-sm">
        {covered.length === 0 ? (
          <span className="text-muted-foreground">No text in this range.</span>
        ) : (
          <>
            <span className="text-muted-foreground">Covers </span>
            <span className="font-medium">{covered[0].title}</span>
            {covered.length > 1 && (
              <>
                <span className="text-muted-foreground"> → </span>
                <span className="font-medium">{covered.at(-1)!.title}</span>
                <span className="text-muted-foreground"> ({covered.length} sections)</span>
              </>
            )}
          </>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          Pages are estimated at {book.words_per_page} words each, like a paperback.
        </p>
      </div>
    </div>
  )
}

function PageInput({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <input
        type="number"
        min={1}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-9 w-28 rounded-lg border border-input bg-background px-3 tabular-nums outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      />
    </label>
  )
}
