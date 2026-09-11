import { useCallback, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { AsyncSection } from '@/components/ui/AsyncSection'
import { Button } from '@/components/ui/Button'
import { PriorityPill } from '@/components/ui/PriorityPill'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import { StatusPill } from '@/components/ui/StatusPill'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/Table'
import { Timestamp } from '@/components/ui/Timestamp'
import { useAuth } from '@/context/AuthContext'
import {
  getServiceRequests,
  getStatuses,
  type Priority,
  type StatusName,
} from '@/lib/api'
import { useAsyncData } from '@/lib/async'

/**
 * Requests Dashboard (`/`) — the post-login landing page, wired to
 * `GET /service-requests` in T-SR-1, replacing the hardcoded mockRequests
 * array.
 *
 * **Two independent async resources, two independent `Async` values.** The
 * request list and the status filter's options come from different endpoints
 * with different failure modes and different auth requirements (`/statuses` is
 * public per ST-1, the list needs a session per SR-1). Sharing one pending
 * flag would let a slow or failed `/statuses` blank a table that had already
 * arrived — so they never do.
 *
 * Filter options for status are **fetched**, not hardcoded: SR-3 answers an
 * unrecognised name with a `422`, so a list of four strings typed out here
 * would produce a broken filter rather than an empty result the day the seed
 * changes. Priority is hardcoded on purpose — SR-4's set is a CHECK
 * constraint, not a lookup table. The asymmetry is deliberate.
 *
 * Layout: bounded to the table/dashboard width and centered per
 * design-tokens.md "Content width" (the shared .content-dashboard class).
 * Below --bp-mobile the priority and date columns drop via `hidden
 * md:table-cell` — the same Table with fewer columns, not a separate stacked
 * layout.
 */

/** The Select value meaning "don't filter". Radix forbids an empty-string item. */
const ANY = 'any'

const PRIORITY_OPTIONS: { value: Priority; label: string }[] = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

export default function RequestsDashboardPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  // SR-2 gives an admin every request, and the nav has exactly one dashboard
  // item — so an admin reading "My requests" would be looking at everyone's.
  // Fixed with copy on this one page rather than a "My / All" toggle or a
  // `?requestor_id=me` param: no designed surface consumes either, and they'd
  // arrive without a consumer.
  const isAdmin = user?.role === 'admin'

  const [status, setStatus] = useState<StatusName | typeof ANY>(ANY)
  const [priority, setPriority] = useState<Priority | typeof ANY>(ANY)
  const [page, setPage] = useState(1)

  const requests = useAsyncData(
    (signal) =>
      getServiceRequests(
        {
          page,
          status: status === ANY ? undefined : status,
          priority: priority === ANY ? undefined : priority,
        },
        signal,
      ),
    [page, status, priority],
  )

  // No deps: the seeded statuses don't change while the page is open.
  const statuses = useAsyncData((signal) => getStatuses(signal), [])

  // Any filter change resets to page 1. Keeping the page number would ask for
  // page 3 of a result set that may only have one, and the server would
  // honestly answer with nothing — a filter that looks broken.
  const changeStatus = useCallback((value: string) => {
    setStatus(value as StatusName | typeof ANY)
    setPage(1)
  }, [])

  const changePriority = useCallback((value: string) => {
    setPriority(value as Priority | typeof ANY)
    setPage(1)
  }, [])

  return (
    <AppShell>
      <div className="content-dashboard flex flex-col gap-6">
        <header className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="flex flex-col gap-1">
            <h1 className="text-h2 font-semibold text-text-primary">
              {isAdmin ? 'All requests' : 'My requests'}
            </h1>
            <p className="text-dense text-text-secondary">
              {isAdmin
                ? 'Every request submitted to the service desk, newest first.'
                : 'Track the status of the requests you have submitted.'}
            </p>
          </div>
          <Button asChild className="self-start">
            <Link to="/requests/new">New request</Link>
          </Button>
        </header>

        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <FilterField label="Status" htmlFor="dashboard-filter-status">
            <Select value={status} onValueChange={changeStatus}>
              <SelectTrigger id="dashboard-filter-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Any status</SelectItem>
                {/*
                 * Options appear as `/statuses` answers, and their absence
                 * never blocks the table — the worst a failed call does here
                 * is leave "Any status" as the only choice, which is exactly
                 * the unfiltered view the page already shows.
                 */}
                {statuses.status === 'ready'
                  ? statuses.data.items.map((option) => (
                      <SelectItem key={option.id} value={option.name}>
                        <StatusPill status={option.name} />
                      </SelectItem>
                    ))
                  : null}
              </SelectContent>
            </Select>
          </FilterField>

          <FilterField label="Priority" htmlFor="dashboard-filter-priority">
            <Select value={priority} onValueChange={changePriority}>
              <SelectTrigger id="dashboard-filter-priority">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>Any priority</SelectItem>
                {PRIORITY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </FilterField>
        </div>

        <AsyncSection state={requests} loadingLabel="Loading requests…">
          {(data) =>
            // Empty is `ready` with an empty array, not a fourth state — and
            // what it means depends on why: a filtered list that matched
            // nothing is a different fact from an account with no requests.
            data.items.length === 0 ? (
              <EmptyState
                filtered={status !== ANY || priority !== ANY}
                isAdmin={isAdmin}
              />
            ) : (
              <div className="flex flex-col gap-4">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Title</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="hidden md:table-cell">
                        Priority
                      </TableHead>
                      {/*
                       * Shows and sorts by the same field. SR-15 orders by
                       * `created_at DESC`, so a column showing `updated_at`
                       * would make a correctly sorted list look shuffled.
                       */}
                      <TableHead className="hidden md:table-cell">
                        Submitted
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {data.items.map((request) => (
                      <TableRow
                        key={request.id}
                        onClick={() => navigate(`/requests/${request.id}`)}
                        className="cursor-pointer hover:bg-card"
                      >
                        <TableCell>
                          {/*
                           * A real link so the row is keyboard-reachable and
                           * open-in-new-tab works; the row-level onClick above
                           * is mouse-only sugar. stopPropagation keeps a link
                           * click from also firing the row handler (same
                           * destination, avoids a double navigate).
                           */}
                          <Link
                            to={`/requests/${request.id}`}
                            onClick={(event) => event.stopPropagation()}
                            className="font-semibold text-text-primary hover:underline"
                          >
                            {request.title}
                          </Link>
                        </TableCell>
                        <TableCell>
                          <StatusPill status={request.status.name} />
                        </TableCell>
                        <TableCell className="hidden md:table-cell">
                          <PriorityPill priority={request.priority} />
                        </TableCell>
                        <TableCell className="hidden text-text-secondary md:table-cell">
                          <Timestamp value={request.created_at} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                <Pagination
                  total={data.total}
                  page={data.page}
                  pageSize={data.page_size}
                  shown={data.items.length}
                  onChange={setPage}
                />
              </div>
            )
          }
        </AsyncSection>
      </div>
    </AppShell>
  )
}

/**
 * Label + control, the filter-bar counterpart to Field.tsx.
 *
 * Not Field itself: that one exists to render react-hook-form's per-field
 * errors and takes an `error` prop these controls have no source for. Local to
 * this page because it is the only filter bar in the app — if a second one
 * appears, that is the moment to extract it, not now.
 */
function FilterField({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: ReactNode
}) {
  return (
    <div className="flex flex-col gap-1 md:w-48">
      <label
        htmlFor={htmlFor}
        className="text-dense font-semibold text-text-primary"
      >
        {label}
      </label>
      {children}
    </div>
  )
}

/**
 * The three honest ways this list is empty, told apart.
 *
 * "No requests match these filters" and "you haven't submitted anything yet"
 * are different facts, and only one of them means the user should change what
 * they did. The admin variant matters for the same reason the heading does:
 * an admin seeing "you haven't submitted a request" while looking at a page
 * that shows everyone's would be reading a different lie.
 */
function EmptyState({
  filtered,
  isAdmin,
}: {
  filtered: boolean
  isAdmin: boolean
}) {
  if (filtered) {
    return (
      <p className="rounded-card border border-border bg-card px-3 py-6 text-center text-dense text-text-secondary">
        No requests match these filters.
      </p>
    )
  }

  return (
    <p className="rounded-card border border-border bg-card px-3 py-6 text-center text-dense text-text-secondary">
      {isAdmin
        ? 'No requests have been submitted yet.'
        : 'You haven’t submitted any requests yet. Use “New request” to raise one.'}
    </p>
  )
}

/**
 * Prev / next plus a count, driven entirely by XC-10's envelope.
 *
 * Without this a user past the default page size of 20 sees the first page and
 * nothing at all indicating the rest exist — the list just stops. `total` and
 * `page_size` come from the response rather than from constants here, so a
 * `page_size` the server clamped (XC-11) is reported as what was actually
 * applied, not as what was asked for.
 */
function Pagination({
  total,
  page,
  pageSize,
  shown,
  onChange,
}: {
  total: number
  page: number
  pageSize: number
  shown: number
  onChange: (page: number) => void
}) {
  const first = (page - 1) * pageSize + 1
  // Counted from what actually arrived rather than `page * pageSize`, which
  // over-reports on the last page.
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
