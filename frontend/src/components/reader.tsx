import { Eye, EyeOff } from 'lucide-react'

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { cn } from '@/lib/utils'

export type Aids = { pinyin: boolean; english: boolean }

/** One sentence pair styled like the generated EPUB: hanzi first, aids subdued. */
export function SentencePair({ html, en, className }: { html: string; en: string; className?: string }) {
  return (
    <div className={cn('pair', className)}>
      <p className="zh" dangerouslySetInnerHTML={{ __html: html }} />
      <p className="en">{en}</p>
    </div>
  )
}

export function ReaderSurface({
  aids,
  className,
  children,
}: {
  aids: Aids
  className?: string
  children: React.ReactNode
}) {
  return (
    <div className={cn('reader', !aids.pinyin && 'hide-pinyin', !aids.english && 'hide-english', className)}>
      {children}
    </div>
  )
}

export function AidsToggle({ aids, onChange }: { aids: Aids; onChange: (aids: Aids) => void }) {
  const value = [aids.pinyin && 'pinyin', aids.english && 'english'].filter(Boolean) as string[]
  return (
    <ToggleGroup
      type="multiple"
      variant="outline"
      size="sm"
      value={value}
      onValueChange={(v) => onChange({ pinyin: v.includes('pinyin'), english: v.includes('english') })}
      aria-label="Reading aids"
    >
      <ToggleGroupItem value="pinyin" aria-label="Show pinyin" className="gap-1.5 px-2.5">
        {aids.pinyin ? <Eye /> : <EyeOff />} Pinyin
      </ToggleGroupItem>
      <ToggleGroupItem value="english" aria-label="Show English" className="gap-1.5 px-2.5">
        {aids.english ? <Eye /> : <EyeOff />} English
      </ToggleGroupItem>
    </ToggleGroup>
  )
}

const r = (pairs: [string, string][]) =>
  '<ruby>' + pairs.map(([c, p]) => `${c}<rt>${p}</rt>`).join('') + '</ruby>'

export const SAMPLE = [
  {
    html:
      r([['她', 'tā']]) +
      r([['推', 'tuī'], ['开', 'kāi']]) +
      r([['门', 'mén']]) +
      '，' +
      r([['走', 'zǒu'], ['了', 'le']]) +
      r([['进', 'jìn'], ['去', 'qù']]) +
      '。',
    en: 'She pushed the door open and walked in.',
  },
  {
    html:
      r([['每', 'měi']]) +
      r([['个', 'gè']]) +
      r([['灯', 'dēng'], ['笼', 'long']]) +
      r([['都', 'dōu']]) +
      r([['需', 'xū'], ['要', 'yào']]) +
      r([['一', 'yí']]) +
      r([['个', 'gè']]) +
      r([['故', 'gù'], ['事', 'shi']]) +
      '。',
    en: 'Every lantern needs a story.',
  },
]
