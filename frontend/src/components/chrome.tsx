import { Moon, Sun } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { href } from '@/lib/router'
import { useTheme } from '@/lib/store'
import { cn } from '@/lib/utils'

export function Logo({ className }: { className?: string }) {
  return (
    <a href={href.library()} className={cn('flex items-center gap-2.5', className)}>
      <span className="flex size-8 items-center justify-center rounded-lg bg-primary font-[family-name:var(--font-hanzi)] text-lg text-primary-foreground shadow-sm">
        字
      </span>
      <span className="font-semibold tracking-tight">Hanzi Reader</span>
    </a>
  )
}

export function ThemeToggle() {
  const [theme, setTheme] = useTheme()
  const next = theme === 'dark' ? 'light' : 'dark'
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button variant="ghost" size="icon" onClick={() => setTheme(next)} aria-label={`Switch to ${next} mode`}>
          {theme === 'dark' ? <Sun /> : <Moon />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</TooltipContent>
    </Tooltip>
  )
}

/** Sticky top bar shared by the library and wizard pages. */
export function TopBar({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <header className={cn('sticky top-0 z-30 border-b bg-background/85 backdrop-blur', className)}>
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:px-6">{children}</div>
    </header>
  )
}
