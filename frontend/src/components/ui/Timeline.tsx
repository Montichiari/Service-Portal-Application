import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/**
 * Vertical stepper. Each step renders a dot — filled (reached) or hollow
 * (pending) — joined to the next by a vertical rule. The caller decides
 * filled vs. hollow; this component only draws it.
 *
 * design-tokens.md specifies no dot/line colours, so these derive from the
 * base palette: --accent for a filled dot, --border for a hollow ring and
 * the connector.
 *
 * `label` and `meta` are `ReactNode` rather than strings (T-SC-1). Both would
 * otherwise force a caller to format something twice over: a status label is
 * StatusPill's to render (design.md §0 decision 4 puts that mapping in exactly
 * one place), and a timestamp is Timestamp's, which is what guarantees the
 * `<time dateTime>` wrapper around it. A `string` here would mean a second
 * status-label table and a formatted date with no machine-readable form.
 */
export interface TimelineStep {
  /** Stable key — the id of whatever the step stands for, never an index. */
  id: string
  label: ReactNode
  meta?: ReactNode
  filled: boolean
}

export interface TimelineProps {
  steps: TimelineStep[]
  className?: string
}

export function Timeline({ steps, className }: TimelineProps) {
  return (
    <ol className={cn('flex flex-col', className)}>
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1
        return (
          <li
            key={step.id}
            className="grid grid-cols-[auto_1fr] gap-x-3"
          >
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  'mt-1 size-3 shrink-0 rounded-full border-2',
                  step.filled
                    ? 'border-accent bg-accent'
                    : 'border-border bg-card',
                )}
                aria-hidden
              />
              {!isLast && <span className="w-0.5 grow bg-border" aria-hidden />}
            </div>
            <div className={cn('pb-6', isLast && 'pb-0')}>
              <div className="text-body font-semibold text-text-primary">
                {step.label}
              </div>
              {step.meta ? (
                <div className="text-dense text-text-secondary">{step.meta}</div>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
