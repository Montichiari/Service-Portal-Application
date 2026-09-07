import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Token-styled native <textarea>. forwardRef + prop spread for direct
 * react-hook-form `register` binding. No label / error markup (Task 1 scope).
 */
const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.ComponentProps<'textarea'>
>(({ className, ...props }, ref) => {
  return (
    <textarea
      ref={ref}
      className={cn(
        'flex min-h-20 w-full rounded-card border border-border bg-card px-3 py-2 text-body text-text-primary outline-none transition-colors',
        'placeholder:text-text-secondary',
        'focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent',
        'disabled:cursor-not-allowed disabled:opacity-50',
        'aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger',
        className,
      )}
      {...props}
    />
  )
})
Textarea.displayName = 'Textarea'

export { Textarea }
