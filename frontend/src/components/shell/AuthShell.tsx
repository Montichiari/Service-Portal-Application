import type { ReactNode } from 'react'
import { Card } from '@/components/ui/Card'
import { cn } from '@/lib/utils'

/**
 * Centered ~400px card on the plain surface — no sidebar. Wraps Login and
 * Register only; never reused for in-app pages (that's AppShell).
 */
export interface AuthShellProps {
  children: ReactNode
  className?: string
}

export function AuthShell({ children, className }: AuthShellProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface p-6">
      <Card className={cn('w-auth-card max-w-full', className)}>{children}</Card>
    </div>
  )
}
