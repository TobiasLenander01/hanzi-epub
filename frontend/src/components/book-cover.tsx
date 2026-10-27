import { libraryCoverUrl } from '@/lib/api'
import { cn } from '@/lib/utils'

// Cloth colours of traditional thread-bound books.
const CLOTH = [
  ['oklch(0.36 0.07 255)', 'oklch(0.3 0.06 260)'], // indigo
  ['oklch(0.47 0.15 30)', 'oklch(0.39 0.13 28)'], // vermilion
  ['oklch(0.42 0.06 165)', 'oklch(0.35 0.05 170)'], // jade
  ['oklch(0.36 0.07 330)', 'oklch(0.3 0.06 330)'], // plum
  ['oklch(0.5 0.09 70)', 'oklch(0.42 0.08 65)'], // ochre
  ['oklch(0.3 0.02 60)', 'oklch(0.25 0.02 60)'], // ink
]

function hash(text: string) {
  let h = 0
  for (const c of text) h = (h * 31 + c.charCodeAt(0)) >>> 0
  return h
}

type Props = {
  id: string
  title: string
  titleZh: string
  author: string
  hasCover: boolean
  className?: string
}

/** The book's own cover, or a generated one styled like a thread-bound Chinese book. */
export function BookCover({ id, title, titleZh, author, hasCover, className }: Props) {
  const base = cn('@container relative aspect-[2/3] overflow-hidden rounded-md shadow-md ring-1 ring-black/10', className)
  if (hasCover) {
    return (
      <div className={base}>
        <img src={libraryCoverUrl(id)} alt="" className="size-full object-cover" loading="lazy" />
      </div>
    )
  }

  const [from, to] = CLOTH[hash(title) % CLOTH.length]
  const label = (titleZh || title).replace(/[《》「」]/g, '').slice(0, 9)
  return (
    <div className={base} style={{ background: `linear-gradient(160deg, ${from}, ${to})` }}>
      {/* stitched spine */}
      <div className="absolute inset-y-0 right-[7%] w-px border-r border-dashed border-white/25" />
      {[18, 38, 62, 82].map((top) => (
        <div key={top} className="absolute right-[7%] h-px w-[7%] bg-white/25" style={{ top: `${top}%` }} />
      ))}
      {/* title slip */}
      <div className="absolute top-[7%] left-[10%] flex h-[58%] w-[24%] justify-center rounded-[2px] bg-[oklch(0.96_0.02_85)] py-[6%] shadow-sm">
        <span
          className="font-[family-name:var(--font-hanzi)] leading-none font-bold text-[oklch(0.25_0.02_50)] [writing-mode:vertical-rl]"
          // fill the slip: it is ~24cqw wide and ~80cqw tall inside its padding
          style={{ fontSize: `${Math.min(15, 72 / (label.length * 1.12))}cqw`, letterSpacing: '0.12em' }}
        >
          {label}
        </span>
      </div>
      <div className="absolute right-[16%] bottom-[6%] left-[10%] text-white/85">
        <p className="line-clamp-3 font-serif text-[clamp(0.6rem,7cqw,0.95rem)] leading-tight">{title}</p>
        {author && <p className="mt-1 truncate text-[clamp(0.5rem,5.5cqw,0.75rem)] text-white/60">{author}</p>}
      </div>
    </div>
  )
}
