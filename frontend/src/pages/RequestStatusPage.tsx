import { zodResolver } from '@hookform/resolvers/zod'
import { useCallback, useState } from 'react'
import { Controller, useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { AsyncSection } from '@/components/ui/AsyncSection'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { Field } from '@/components/ui/Field'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/Select'
import { StatusPill } from '@/components/ui/StatusPill'
import { Textarea } from '@/components/ui/Textarea'
import { Timeline, type TimelineStep } from '@/components/ui/Timeline'
import { Timestamp } from '@/components/ui/Timestamp'
import { useAuth } from '@/context/AuthContext'
import {
  createStatusChange,
  getServiceRequest,
  getStatusChanges,
  getStatuses,
  MAX_PAGE_SIZE,
  type Status,
  type StatusChange,
} from '@/lib/api'
import { useAsyncData } from '@/lib/async'
import { applyFieldErrors, pageErrorMessage } from '@/lib/formErrors'
import { fullName } from '@/lib/names'
import {
  statusChangeSchema,
  type StatusChangeValues,
} from '@/schemas/statusChangeSchema'

/**
 * Track Request Status (`/requests/:id/status`) — wired to real data in T-SC-1,
 * replacing the prototype's fixed five-row template of `null` placeholders
 * (frontend-contract.md §7.2).
 *
 * **The stepper is a client-side merge** (design.md §5): `GET /statuses` gives
 * every step that exists, `GET .../status-changes` gives the ones this request
 * has actually reached, and a status with no matching transition is drawn
 * hollow. The merge lives here because SC-3 forbids the API inventing rows for
 * un-reached steps — it reports what happened, and what *hasn't* happened yet
 * is a question only the full status list can answer.
 *
 * SR-14 means there is always a real first step: creating a request writes its
 * `open` transition in the same transaction. So nothing here synthesises a row
 * and there is no "the first step is always filled" special case — a brand-new
 * request draws one filled step because one really exists.
 *
 * The prototype's `STATUS_HISTORY_LABELS` and its five-state
 * `StatusHistoryState` vocabulary are gone with it. The backend has four
 * statuses and no `assigned` state, and 'Assigned to IT Service Desk' had no
 * assignment data behind it at all (`assignee` is null this whole phase).
 * Deleting it also settles frontend-contract.md §9-#8's two-non-matching-enums
 * problem, since only `StatusName` survives.
 *
 * Layout: bounded to the 720px detail-view width and centered in the content
 * area per design-tokens.md "Content width" (the shared .content-detail class).
 * AppShell owns the surrounding padding.
 */
export default function RequestStatusPage() {
  const { id } = useParams()
  // `id` is always present — the route pattern that mounts this page declares
  // it — but useParams cannot know that, and `''` fetches a malformed id,
  // which SR-13 answers with the same 404 as any other miss.
  const requestId = id ?? ''

  const request = useAsyncData(
    (signal) => getServiceRequest(requestId, signal),
    [requestId],
  )

  // Same panel RequestDetailsPage shows, for the same reason: a 404 is an
  // answer about this request rather than a failure to reach the server, and
  // the API's bare "Not found." in an error banner tells the reader nothing
  // about what to do.
  if (request.status === 'error' && request.error.code === 'NOT_FOUND') {
    return (
      <AppShell>
        <div className="content-detail flex flex-col gap-6">
          <header className="flex flex-col gap-1">
            <h1 className="text-h2 font-semibold text-text-primary">
              Request not found
            </h1>
            <p className="text-dense text-text-secondary">
              This request doesn’t exist, or it isn’t one you have access to.
            </p>
          </header>
          <Link
            to="/"
            className="self-start text-dense font-semibold text-accent hover:underline"
          >
            Back to your requests
          </Link>
        </div>
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="content-detail flex flex-col gap-6">
        <AsyncSection state={request} loadingLabel="Loading request…">
          {(data) => (
            <div className="flex flex-col gap-6">
              <header className="flex flex-col gap-2">
                <p className="text-dense break-all text-text-secondary">
                  Request {data.id}
                </p>
                {/*
                 * The real title, restored now that it sits above real data.
                 * T-SR-1 dropped it deliberately rather than fetch the request
                 * just to head an invented timeline, which would have read as
                 * more trustworthy than it was (task-log.md#t-sr-1).
                 */}
                <h1 className="text-h2 font-semibold text-text-primary">
                  {data.title}
                </h1>
              </header>

              {/*
               * Mounted inside the ready branch, so the sub-resource is asked
               * for only once its parent is known to be visible. SC-2's
               * predicate is SR-12's, so firing both at once would mean two
               * independent 404 surfaces racing to explain one fact — the same
               * reasoning T-CM-1 applied to comments.
               */}
              <StatusHistory requestId={data.id} />

              <Link
                to={`/requests/${data.id}`}
                className="self-start text-dense font-semibold text-accent hover:underline"
              >
                Back to request details
              </Link>
            </div>
          )}
        </AsyncSection>
      </div>
    </AppShell>
  )
}

/**
 * Every page of this request's transitions, as one array.
 *
 * The stepper is a merge against the *whole* history, not against a page of it:
 * with only the first page, a status reached on transition 21 would draw hollow
 * — a step the request has demonstrably passed through, rendered as one it
 * hasn't. That is precisely the kind of quiet lie SC-3 exists to prevent, so
 * paging is drained here rather than exposed to the caller.
 *
 * `page_size` is read back off the response rather than assumed: XC-11 clamps
 * what was asked for, so the count of pages has to be computed from what the
 * server actually applied.
 */
async function loadStatusHistory(
  requestId: string,
  signal: AbortSignal,
): Promise<StatusChange[]> {
  const first = await getStatusChanges(
    requestId,
    { page: 1, page_size: MAX_PAGE_SIZE },
    signal,
  )
  const items = [...first.items]

  const pages = Math.ceil(first.total / first.page_size)
  for (let page = 2; page <= pages; page += 1) {
    const next = await getStatusChanges(
      requestId,
      { page, page_size: first.page_size },
      signal,
    )
    items.push(...next.items)
  }

  return items
}

/**
 * Build the stepper: one step per seeded status, filled where this request has
 * a real transition to it.
 *
 * `statuses` is used in the order it arrives — ST-2 guarantees `sort_order`
 * ascending, and re-sorting here would be a second opinion about the same
 * thing. Transitions arrive `changed_at` ascending (SC-1), so writing each into
 * the map in order leaves the **most recent** visit to a status as the one
 * shown: a request reopened after being resolved should show when it was last
 * moved there, not the first time.
 */
function buildSteps(statuses: Status[], changes: StatusChange[]): TimelineStep[] {
  const latest = new Map<string, StatusChange>()
  for (const change of changes) {
    latest.set(change.status.id, change)
  }

  return statuses.map((status) => {
    const change = latest.get(status.id)
    return {
      id: status.id,
      // StatusPill owns the label, here as everywhere else — a status name
      // arrives as a raw identifier (`in_progress`) and exactly one table in
      // the frontend turns it into prose (design.md §0 decision 4).
      label: <StatusPill status={status.name} />,
      meta:
        change === undefined ? (
          // Said out loud rather than left to the hollow dot alone: the dot is
          // `aria-hidden`, so without this a screen reader would read a
          // reached step and an un-reached one identically.
          <span>Not yet reached</span>
        ) : (
          <div className="flex flex-col gap-0.5">
            <span>
              <Timestamp value={change.changed_at} withTime />
              {/*
               * Null when the admin who made the change has since been deleted
               * (design.md §5's ON DELETE SET NULL) — the transition keeps its
               * record and loses its actor, so the line simply omits the name
               * rather than inventing one.
               */}
              {change.changed_by === null
                ? null
                : ` · ${fullName(change.changed_by)}`}
            </span>
            {change.note === null ? null : (
              <span className="whitespace-pre-line">{change.note}</span>
            )}
          </div>
        ),
      filled: change !== undefined,
    }
  })
}

/**
 * The stepper and, for an admin, the control that adds to it.
 *
 * **Two resources, two `Async` values** (frontend/CLAUDE.md's Async state
 * rule). Unlike the dashboard's pair these are both required to draw anything —
 * the merge needs the full status list *and* the history — so they compose as
 * nested AsyncSections rather than one blanking the other. They are still two
 * independent fetches issued together, not one flag covering both.
 */
function StatusHistory({ requestId }: { requestId: string }) {
  const { user } = useAuth()
  // SC-4: only an admin may transition a request. This gates the control, never
  // the outcome — a client that got this wrong would produce a rejected submit,
  // not a status change, because the server answers 403 regardless.
  const isAdmin = user?.role === 'admin'

  // No deps: the seeded statuses don't change while the page is open.
  const statuses = useAsyncData((signal) => getStatuses(signal), [])
  const history = useAsyncData(
    (signal) => loadStatusHistory(requestId, signal),
    [requestId],
  )

  /*
   * Transitions posted since the history was fetched.
   *
   * Held here rather than refetched, per frontend/CLAUDE.md's Async state rule:
   * a refetch returns the list to `pending` and AsyncSection would replace the
   * stepper with a loading line, so an admin would watch the change they just
   * made take the whole timeline away with it. What is appended is the `201`
   * body itself, so nothing on screen is invented client-side.
   *
   * Keyed by request alone — unlike T-CM-1's comments, which key by page too,
   * because this fetch drains every page and so has no page to key on.
   */
  const [posted, setPosted] = useState<{ key: string; items: StatusChange[] }>({
    key: requestId,
    items: [],
  })
  const appended = posted.key === requestId ? posted.items : []

  const addPosted = useCallback(
    (change: StatusChange) => {
      setPosted((previous) =>
        previous.key === requestId
          ? { key: requestId, items: [...previous.items, change] }
          : { key: requestId, items: [change] },
      )
    },
    [requestId],
  )

  return (
    <Card>
      <h2 className="text-subhead font-semibold text-text-primary">
        Status history
      </h2>

      <AsyncSection state={statuses} loadingLabel="Loading statuses…">
        {(statusList) => (
          <AsyncSection state={history} loadingLabel="Loading status history…">
            {(changes) => (
              <div className="flex flex-col gap-4">
                <Timeline steps={buildSteps(statusList.items, [...changes, ...appended])} />

                {/*
                 * Inside the ready branch: the control exists to add to a
                 * timeline that is on screen, and offering it under an error
                 * banner would accept a transition with nothing to show it on.
                 */}
                {isAdmin ? (
                  <StatusChangeForm
                    requestId={requestId}
                    statuses={statusList.items}
                    onPosted={addPosted}
                  />
                ) : null}
              </div>
            )}
          </AsyncSection>
        )}
      </AsyncSection>
    </Card>
  )
}

// The API-shaped fields this form renders, so a `422` naming anything else
// falls through to the banner rather than into a control that isn't there.
const STATUS_CHANGE_FIELDS = ['status_id', 'note'] as const

/**
 * Move a request to another status (SC-5 to SC-7), admin only.
 *
 * The whole form is **absent from the DOM** for a regular user rather than
 * hidden or disabled — the same rule the internal-comment checkbox and the
 * admin Requestor column follow. A control that is merely invisible still reads
 * as a control in the accessibility tree.
 *
 * Every seeded status is offered, including the one the request is already on:
 * SC-5 accepts that, and a re-entry is a real event an admin may want on the
 * record (with a note explaining it). Filtering the list here would be this
 * page inventing a transition rule the API doesn't have.
 */
function StatusChangeForm({
  requestId,
  statuses,
  onPosted,
}: {
  requestId: string
  statuses: Status[]
  onPosted: (change: StatusChange) => void
}) {
  const [formError, setFormError] = useState<string | null>(null)
  const {
    control,
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<StatusChangeValues>({
    resolver: zodResolver(statusChangeSchema),
    defaultValues: { status_id: '', note: '' },
  })

  const onValidSubmit = async (values: StatusChangeValues) => {
    setFormError(null)
    try {
      const created = await createStatusChange(requestId, {
        status_id: values.status_id,
        // Omitted rather than sent as '': SC-7 stores the note verbatim, and
        // an empty string is a note that says nothing, not the absence of one.
        note: values.note === '' ? undefined : values.note,
      })
      reset()
      onPosted(created)
    } catch (error) {
      // SC-6's `422` lands inline on `status_id`; a `403` (SC-4) or a `404`
      // (SC-8) isn't attributable to a field and surfaces as the server's own
      // message in the banner.
      if (!applyFieldErrors(error, setError, STATUS_CHANGE_FIELDS)) {
        setFormError(pageErrorMessage(error))
      }
    }
  }

  return (
    <form
      className="flex flex-col gap-3 border-t border-border pt-4"
      noValidate
      onSubmit={handleSubmit(onValidSubmit)}
    >
      <h3 className="text-dense font-semibold text-text-primary">
        Change status
      </h3>

      {formError !== null ? <ErrorBanner message={formError} /> : null}

      <Field
        label="New status"
        htmlFor="status-change-status"
        error={errors.status_id?.message}
      >
        <Controller
          control={control}
          name="status_id"
          render={({ field }) => (
            <Select value={field.value} onValueChange={field.onChange}>
              <SelectTrigger
                id="status-change-status"
                aria-invalid={errors.status_id ? true : undefined}
                onBlur={field.onBlur}
              >
                <SelectValue placeholder="Select a status" />
              </SelectTrigger>
              <SelectContent>
                {/*
                 * Options are the `statuses` rows themselves, so the id posted
                 * is one the table holds by construction — SC-6's 422 is for
                 * callers that go around this form, not something a user can
                 * reach through it.
                 */}
                {statuses.map((status) => (
                  <SelectItem key={status.id} value={status.id}>
                    <StatusPill status={status.name} />
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
      </Field>

      <Field
        label="Note (optional)"
        htmlFor="status-change-note"
        error={errors.note?.message}
      >
        <Textarea
          id="status-change-note"
          aria-invalid={errors.note ? true : undefined}
          {...register('note', { onChange: () => setFormError(null) })}
        />
      </Field>

      {/* Disabled for the duration of the request, not merely after it
          succeeds — against a real endpoint a second click records a second
          transition, the same correctness fix T-AUTH-5, T-SR-1 and T-CM-1 made
          to their forms. */}
      <Button type="submit" className="self-start" disabled={isSubmitting}>
        {isSubmitting ? 'Saving…' : 'Update status'}
      </Button>
    </form>
  )
}
