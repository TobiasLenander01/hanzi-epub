import { useCallback, useEffect, useState } from 'react'
import { BookOpen, BookPlus, Download, Languages, MoreHorizontal, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { BookCover } from '@/components/book-cover'
import { Logo, ThemeToggle, TopBar } from '@/components/chrome'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Progress } from '@/components/ui/progress'
import { Skeleton } from '@/components/ui/skeleton'
import { type LibraryBook, deleteBook, getLibrary, libraryEpubUrl } from '@/lib/api'
import { href } from '@/lib/router'
import { type Progress as ReadingProgress, progressStore } from '@/lib/store'

function readingFraction(book: LibraryBook, p: ReadingProgress | undefined) {
  if (!p || book.keys.length === 0) return 0
  const i = book.keys.indexOf(p.key)
  if (i < 0) return 0
  return (i + p.fraction) / Math.max(book.keys.length, book.source_chapters)
}

export function LibraryPage() {
  const [books, setBooks] = useState<LibraryBook[] | null>(null)
  const [deleting, setDeleting] = useState<LibraryBook | null>(null)
  const progress = progressStore.use()

  const load = useCallback(() => {
    getLibrary()
      .then(setBooks)
      .catch((e) => {
        setBooks((b) => b ?? [])
        toast.error((e as Error).message)
      })
  }, [])

  useEffect(load, [load])
  // keep cards fresh while books are being translated
  const converting = books?.some((b) => b.converting)
  useEffect(() => {
    const id = setInterval(load, converting ? 3000 : 20000)
    window.addEventListener('focus', load)
    return () => {
      clearInterval(id)
      window.removeEventListener('focus', load)
    }
  }, [load, converting])

  const current = books
    ?.filter((b) => progress[b.id])
    .sort((a, b) => progress[b.id].at - progress[a.id].at)[0]

  return (
    <div className="min-h-svh">
      <TopBar>
        <Logo />
        <div className="ml-auto flex items-center gap-1.5">
          <ThemeToggle />
          <Button asChild className="gap-1.5">
            <a href={href.add()}>
              <Plus /> <span className="hidden sm:inline">Add book</span>
              <span className="sm:hidden">Add</span>
            </a>
          </Button>
        </div>
      </TopBar>

      <main className="mx-auto max-w-6xl space-y-10 px-4 py-8 sm:px-6 sm:py-10">
        {books === null ? (
          <GridSkeleton />
        ) : books.length === 0 ? (
          <EmptyLibrary />
        ) : (
          <>
            {current && <ContinueCard book={current} progress={progress[current.id]} />}
            <section className="space-y-5">
              <div className="flex items-baseline justify-between gap-4">
                <h2 className="text-xl font-semibold tracking-tight">Your library</h2>
                <p className="text-sm text-muted-foreground">
                  {books.length} {books.length === 1 ? 'book' : 'books'}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 sm:gap-x-6 md:grid-cols-4 lg:grid-cols-5">
                {books.map((b) => (
                  <BookCard
                    key={b.id}
                    book={b}
                    fraction={readingFraction(b, progress[b.id])}
                    onDelete={() => setDeleting(b)}
                  />
                ))}
                <AddTile />
              </div>
            </section>
          </>
        )}
      </main>

      <AlertDialog open={!!deleting} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove “{deleting?.title}”?</AlertDialogTitle>
            <AlertDialogDescription>
              Its translated chapters will be deleted from your library. You can translate the book again later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={async () => {
                if (!deleting) return
                try {
                  await deleteBook(deleting.id)
                  progressStore.set(({ [deleting.id]: _, ...rest }) => rest)
                  load()
                } catch (e) {
                  toast.error((e as Error).message)
                }
              }}
            >
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function ContinueCard({ book, progress }: { book: LibraryBook; progress: ReadingProgress }) {
  const fraction = readingFraction(book, progress)
  const chapterNo = book.keys.indexOf(progress.key) + 1
  return (
    <Card className="paper-grain animate-in fade-in slide-in-from-bottom-2 flex-row items-center gap-5 overflow-hidden p-4 duration-500 sm:gap-7 sm:p-6">
      <a href={href.read(book.id)} className="w-20 shrink-0 transition-transform hover:-translate-y-0.5 sm:w-28">
        <BookCover id={book.id} title={book.title} titleZh={book.title_zh} author={book.author} hasCover={book.has_cover} />
      </a>
      <div className="min-w-0 flex-1 space-y-3">
        <div>
          <p className="text-xs font-medium tracking-wide text-primary uppercase">Continue reading</p>
          <h1 className="mt-1 truncate font-[family-name:var(--font-hanzi)] text-2xl font-semibold sm:text-3xl">
            {book.title_zh || book.title}
          </h1>
          <p className="truncate text-sm text-muted-foreground">
            {book.title} · {book.author}
          </p>
        </div>
        <div className="max-w-sm space-y-1.5">
          <Progress value={fraction * 100} className="h-1.5" />
          <p className="text-xs text-muted-foreground tabular-nums">
            Chapter {chapterNo} of {book.keys.length} · {Math.round(fraction * 100)}% of the book
          </p>
        </div>
        <Button asChild size="lg" className="gap-2">
          <a href={href.read(book.id)}>
            <BookOpen /> Continue
          </a>
        </Button>
      </div>
    </Card>
  )
}

function BookCard({ book, fraction, onDelete }: { book: LibraryBook; fraction: number; onDelete: () => void }) {
  const partial = book.keys.length < book.source_chapters
  return (
    <div className="group relative">
      <a
        href={href.read(book.id)}
        className="block rounded-md transition-transform duration-300 outline-none group-hover:-translate-y-1 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <BookCover
          id={book.id}
          title={book.title}
          titleZh={book.title_zh}
          author={book.author}
          hasCover={book.has_cover}
          className="shadow-lg transition-shadow group-hover:shadow-xl"
        />
      </a>
      {book.converting && (
        <div className="pointer-events-none absolute inset-x-2 top-2 flex items-center gap-1.5 rounded-full bg-background/90 px-2.5 py-1 text-xs font-medium shadow backdrop-blur">
          <Languages className="size-3.5 animate-pulse text-primary" />
          Translating {Math.round((book.converting.done / Math.max(1, book.converting.total)) * 100)}%
        </div>
      )}
      <div className="mt-3 flex items-start gap-1">
        <a href={href.read(book.id)} className="min-w-0 flex-1">
          <p className="truncate leading-snug font-medium">{book.title}</p>
          <p className="truncate text-sm text-muted-foreground">
            {partial ? `${book.keys.length} of ${book.source_chapters} chapters` : book.author}
          </p>
        </a>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon-sm" className="-mr-1.5 shrink-0" aria-label="Book options">
              <MoreHorizontal />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuItem asChild>
              <a href={href.read(book.id)}>
                <BookOpen /> Read
              </a>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <a href={libraryEpubUrl(book.id)} download>
                <Download /> Download EPUB
              </a>
            </DropdownMenuItem>
            <DropdownMenuItem asChild>
              <a href={href.add(book.id)}>
                <BookPlus /> Translate more chapters
              </a>
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={onDelete} disabled={!!book.converting}>
              <Trash2 /> Remove from library
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      {fraction > 0 && <Progress value={fraction * 100} className="mt-2 h-1" />}
    </div>
  )
}

function AddTile() {
  return (
    <a
      href={href.add()}
      className="flex aspect-[2/3] flex-col items-center justify-center gap-3 rounded-md border-2 border-dashed text-muted-foreground transition-colors hover:border-primary/50 hover:bg-accent/40 hover:text-foreground"
    >
      <span className="flex size-12 items-center justify-center rounded-full bg-primary/10 text-primary">
        <Plus className="size-6" />
      </span>
      <span className="text-sm font-medium">Add a book</span>
    </a>
  )
}

function EmptyLibrary() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-5 py-16 text-center">
      <div className="reader">
        <p className="zh !text-4xl">
          <ruby>
            读<rt>dú</rt>
            书<rt>shū</rt>
          </ruby>
        </p>
      </div>
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">Your library is empty</h1>
        <p className="text-muted-foreground">
          Add an English EPUB and it comes back as a Chinese reader: hanzi first, pinyin above, English below.
        </p>
      </div>
      <Button asChild size="lg" className="gap-2">
        <a href={href.add()}>
          <Plus /> Add your first book
        </a>
      </Button>
    </div>
  )
}

function GridSkeleton() {
  return (
    <div className="grid grid-cols-2 gap-x-4 gap-y-8 sm:grid-cols-3 sm:gap-x-6 md:grid-cols-4 lg:grid-cols-5">
      {Array.from({ length: 5 }, (_, i) => (
        <div key={i} className="space-y-3">
          <Skeleton className="aspect-[2/3] w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ))}
    </div>
  )
}
