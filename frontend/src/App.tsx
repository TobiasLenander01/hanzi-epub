import { useEffect } from 'react'

import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import { LibraryPage } from '@/pages/library'
import { ReaderPage } from '@/pages/reader'
import { WizardPage } from '@/pages/wizard'
import { useRoute } from '@/lib/router'

export default function App() {
  const route = useRoute()

  useEffect(() => {
    if (route.page !== 'read') window.scrollTo({ top: 0 })
  }, [route.page])

  return (
    <TooltipProvider delayDuration={300}>
      {route.page === 'library' && <LibraryPage />}
      {route.page === 'read' && <ReaderPage key={route.bookId} bookId={route.bookId} chapterKey={route.key} />}
      {route.page === 'add' && <WizardPage key={route.libraryId ?? 'new'} libraryId={route.libraryId} />}
      <Toaster position="top-center" richColors />
    </TooltipProvider>
  )
}
