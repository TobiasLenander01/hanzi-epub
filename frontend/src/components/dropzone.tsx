import { useRef, useState } from 'react'
import { BookUp, Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'

export function Dropzone({ onFile, busy }: { onFile: (file: File) => void; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  const pick = (files: FileList | null) => {
    const file = files?.[0]
    if (file) onFile(file)
  }

  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => input.current?.click()}
      onDragOver={(e) => {
        e.preventDefault()
        setDragging(true)
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragging(false)
        pick(e.dataTransfer.files)
      }}
      className={cn(
        'group relative flex min-h-64 w-full flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed bg-card/70 p-8 text-center transition-all outline-none',
        'hover:border-primary/60 hover:bg-accent/40 focus-visible:ring-3 focus-visible:ring-ring/50',
        dragging && 'scale-[1.01] border-primary bg-accent/60',
        busy && 'cursor-wait',
      )}
    >
      <div
        className={cn(
          'flex size-16 items-center justify-center rounded-2xl bg-primary/10 text-primary transition-transform',
          'group-hover:-translate-y-1 group-hover:rotate-[-4deg]',
          dragging && '-translate-y-1 rotate-[-4deg]',
        )}
      >
        {busy ? <Loader2 className="size-8 animate-spin" /> : <BookUp className="size-8" />}
      </div>
      <div className="space-y-1">
        <p className="text-lg font-medium">{busy ? 'Reading your book…' : 'Drop an English EPUB here'}</p>
        <p className="text-sm text-muted-foreground">
          {busy ? 'Finding chapters and pages' : 'or click to choose a file · DRM-free .epub up to 100 MB'}
        </p>
      </div>
      <input
        ref={input}
        type="file"
        accept=".epub,application/epub+zip"
        className="hidden"
        onChange={(e) => {
          pick(e.target.files)
          e.target.value = ''
        }}
      />
    </button>
  )
}
