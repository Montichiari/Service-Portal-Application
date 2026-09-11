import { formatDate, formatDateTime } from '@/lib/datetime'

/**
 * An API timestamp, rendered for a person and still readable by a machine.
 *
 * The `<time dateTime>` wrapper is the reason this is a component rather than
 * a bare call to lib/datetime.ts: the displayed text is localised and
 * abbreviated, so the exact instant would otherwise be lost to anything that
 * isn't a pair of eyes. Going through here means no page can format a
 * timestamp and forget the element.
 */
export interface TimestampProps {
  /** ISO 8601, UTC, as XC-2 emits it. */
  value: string
  /** `false` (the default) drops the time of day — see lib/datetime.ts. */
  withTime?: boolean
  className?: string
}

export function Timestamp({ value, withTime = false, className }: TimestampProps) {
  return (
    <time dateTime={value} className={className}>
      {withTime ? formatDateTime(value) : formatDate(value)}
    </time>
  )
}
