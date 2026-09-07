import * as React from 'react'
import { cn } from '@/lib/utils'

/**
 * Thin, token-styled wrapper over a native <input>. forwardRef + full prop
 * spread so `{...register('field')}` from react-hook-form binds directly.
 * Label / inline-error markup is deliberately out of scope for Task 1.
 */
const TextInput = React.forwardRef<
  HTMLInputElement,
  React.ComponentProps<'input'>
>(({ className, type = 'text', ...props }, ref) => {
  return (
    <input
      ref={ref}
      type={type}
      className={cn(
        'flex h-9 w-full rounded-card border border-border bg-card px-3 text-body text-text-primary outline-none transition-colors',
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
TextInput.displayName = 'TextInput'

export { TextInput }
