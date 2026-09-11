import { Button } from '@/components/ui/Button'

/**
 * Prev / next plus a count, driven entirely by XC-10's envelope.
 *
 * Without this a caller past the default page size of 20 sees the first page
 * and nothing at all indicating the rest exist — the list simply stops. That is
 * true of a request list (T-SR-1) and equally true of a conversation (T-CM-1),
 * which is why this moved out of RequestsDashboardPage when the comments list
 * became its second caller: frontend/CLAUDE.md's rule is to extract at the
 * moment a second page needs the same thing, not to schedule it afterwards.
 *
 * `total` and `pageSize` come from the response rather than from constants
 * here, so a `page_size` the server clamped (XC-11) is reported as what was
 * actually applied rather than as what was asked for.
 */
export interface PaginationProps {
  /** XC-10's `total` — what *this caller* can see, not the table's row count. */
  total: number
  page: number
  pageSize: number
  /**
   * How many rows are actually on screen. Counted by the caller rather than as
   * `page * pageSize`, which over-reports on the last page.
   */
  shown: number
  onChange: (page: number) => void
}

export function Pagination({
  total,
  page,
  pageSize,
  shown,
  onChange,
}: PaginationProps) {
  const first = (page - 1) * pageSize + 1
  const last = first + shown - 1
  const hasPrevious = page > 1
  const hasNext = last < total

  return (
    <div className="flex flex-col items-center gap-3 md:flex-row md:justify-between">
      <p className="text-dense text-text-secondary">
        Showing {first}–{last} of {total}
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="secondary"
          disabled={!hasPrevious}
          onClick={() => onChange(page - 1)}
        >
          Previous
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={!hasNext}
          onClick={() => onChange(page + 1)}
        >
          Next
        </Button>
      </div>
    </div>
  )
}
