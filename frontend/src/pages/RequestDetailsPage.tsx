import { zodResolver } from '@hookform/resolvers/zod'
import { useCallback, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useParams } from 'react-router-dom'
import { AppShell } from '@/components/shell/AppShell'
import { AsyncSection } from '@/components/ui/AsyncSection'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { Field } from '@/components/ui/Field'
import { Pagination } from '@/components/ui/Pagination'
import { PriorityPill } from '@/components/ui/PriorityPill'
import { StatusPill } from '@/components/ui/StatusPill'
import { Textarea } from '@/components/ui/Textarea'
import { Timestamp } from '@/components/ui/Timestamp'
import { useAuth } from '@/context/AuthContext'
import { createComment, getComments, getServiceRequest, type Comment } from '@/lib/api'
import { useAsyncData } from '@/lib/async'
import { applyFieldErrors, pageErrorMessage } from '@/lib/formErrors'
import { fullName } from '@/lib/names'
import { commentSchema, type CommentValues } from '@/schemas/commentSchema'

/**
 * View Request Details (`/requests/:id`) — wired to
 * `GET /service-requests/{id}` in T-SR-1, replacing the single hardcoded
 * mockRequestDetail object.
 *
 * The `:id` in the URL is now the request that gets fetched, which closes
 * frontend-contract.md §3.7: the prototype rendered the same object whatever
 * the URL said, so every request in the list led to one identical page. A
 * request the caller may not see comes back `404` (SR-12) — indistinguishable
 * from one that doesn't exist, by design, since leaking existence to someone
 * who can't read it is the thing SR-13 prevents — and that lands on the
 * visible not-found panel below rather than silently rendering something else.
 *
 * Comments arrived in T-CM-1, from their own endpoint rather than from an
 * embedded array (design.md §0 decision 3) — and with a composer, which the
 * prototype never had at all (frontend-contract.md §6.5).
 *
 * Layout: bounded to the 720px detail-view width and centered per
 * design-tokens.md "Content width" (the shared .content-detail class).
 * AppShell owns the surrounding padding.
 */
const REQUEST_TYPE_LABELS: Record<string, string> = { general: 'General' }

export default function RequestDetailsPage() {
  const { id } = useParams()
  // `id` is always present — the route pattern that mounts this page declares
  // it — but useParams cannot know that, and `''` fetches a malformed id,
  // which SR-13 answers with the same 404 as any other miss.
  const requestId = id ?? ''

  const request = useAsyncData(
    (signal) => getServiceRequest(requestId, signal),
    [requestId],
  )

  // A 404 is an answer about this request, not a failure to reach the server,
  // so it gets its own panel rather than AsyncSection's error banner — which
  // would otherwise render the API's bare "Not found." where the user needs to
  // know their link is wrong.
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
                {/*
                 * The full UUID, not a short `#4271`-style number — design.md
                 * §0 decision 8 declined the `ticket_number` column, so this
                 * id is the only identifier the API exposes.
                 */}
                <p className="text-dense break-all text-text-secondary">
                  Request {data.id}
                </p>
                <h1 className="text-h2 font-semibold text-text-primary">
                  {data.title}
                </h1>
              </header>

              <Card>
                <h2 className="text-subhead font-semibold text-text-primary">
                  Details
                </h2>
                <dl className="grid grid-cols-[auto_1fr] items-center gap-x-6 gap-y-3 text-body">
                  <dt className="text-text-secondary">Status</dt>
                  <dd>
                    <StatusPill status={data.status.name} />
                  </dd>

                  <dt className="text-text-secondary">Type</dt>
                  <dd className="text-text-primary">
                    {REQUEST_TYPE_LABELS[data.request_type] ?? data.request_type}
                  </dd>

                  <dt className="text-text-secondary">Priority</dt>
                  <dd>
                    <PriorityPill priority={data.priority} />
                  </dd>

                  <dt className="text-text-secondary">Requested by</dt>
                  <dd className="text-text-primary">{fullName(data.requestor)}</dd>

                  <dt className="text-text-secondary">Assigned to</dt>
                  <dd className="text-text-primary">
                    {/*
                     * Always "Unassigned" this phase: there is no assignment
                     * path and PATCH is deferred (design.md §7). Shown rather
                     * than hidden so the field's existence is honest — and
                     * never filled with an invented placeholder name.
                     */}
                    {data.assignee === null
                      ? 'Unassigned'
                      : fullName(data.assignee)}
                  </dd>

                  <dt className="text-text-secondary">Submitted</dt>
                  <dd className="text-text-primary">
                    <Timestamp value={data.created_at} withTime />
                  </dd>

                  <dt className="text-text-secondary">Last updated</dt>
                  <dd className="text-text-primary">
                    <Timestamp value={data.updated_at} withTime />
                  </dd>
                </dl>
                <Link
                  to={`/requests/${data.id}/status`}
                  className="text-dense font-semibold text-accent hover:underline"
                >
                  View full history
                </Link>
              </Card>

              <Card>
                <h2 className="text-subhead font-semibold text-text-primary">
                  Description
                </h2>
                <p className="text-body whitespace-pre-line text-text-primary">
                  {data.description}
                </p>
              </Card>

              {/*
               * Mounted inside the ready branch, so the sub-resource is asked
               * for only once its parent is known to be visible. CM-4 answers
               * with the same 404 SR-12 gives, so firing both at once would
               * mean two error surfaces racing to explain one fact — and the
               * not-found panel above already says it properly.
               */}
              <RequestComments requestId={data.id} />
            </div>
          )}
        </AsyncSection>
      </div>
    </AppShell>
  )
}

/**
 * The conversation on one request: the list (CM-1 to CM-4) and the composer
 * that adds to it (CM-5 to CM-9).
 *
 * Loading and error come from T-SR-1's `Async` pattern via `useAsyncData` and
 * `AsyncSection` — frontend/CLAUDE.md is explicit that Groups 3 and 4 reuse it
 * rather than invent a second one, and a second shape appearing here would be
 * the sign it was only ever described.
 */
function RequestComments({ requestId }: { requestId: string }) {
  const { user } = useAuth()
  // CM-8: only an admin may mark a comment internal. This gates the control,
  // never the outcome — CM-7 is enforced server-side with a 403, and a client
  // that got this wrong would produce a rejected submit, not an internal note.
  const isAdmin = user?.role === 'admin'

  const [page, setPage] = useState(1)
  const comments = useAsyncData(
    (signal) => getComments(requestId, { page }, signal),
    [requestId, page],
  )

  /*
   * Comments posted since this page of the conversation was fetched.
   *
   * Held here rather than refetched, because a refetch returns the list to
   * `pending` and AsyncSection would replace the conversation with a loading
   * line — the user would watch what they just wrote take the whole thread
   * away with it. Appending shows the server's own response object, so nothing
   * here is invented.
   *
   * Keyed by request *and* page: navigating either one makes these already
   * accounted for in what the server sends back, and keeping them would show
   * them twice.
   */
  const pageKey = `${requestId}:${page}`
  const [posted, setPosted] = useState<{ key: string; items: Comment[] }>({
    key: pageKey,
    items: [],
  })
  const appended = posted.key === pageKey ? posted.items : []

  const addPosted = useCallback(
    (comment: Comment) => {
      setPosted((previous) =>
        previous.key === pageKey
          ? { key: pageKey, items: [...previous.items, comment] }
          : { key: pageKey, items: [comment] },
      )
    },
    [pageKey],
  )

  return (
    <Card>
      <h2 className="text-subhead font-semibold text-text-primary">Comments</h2>

      <AsyncSection state={comments} loadingLabel="Loading comments…">
        {(data) => {
          // Oldest first (CM-1) — the opposite of the dashboard's SR-15 order,
          // because a conversation reads top to bottom. Newly posted ones go
          // at the end for the same reason.
          const items = [...data.items, ...appended]
          const total = data.total + appended.length

          return (
            <div className="flex flex-col gap-4">
              {/*
               * Empty is `ready` with an empty array, not a fourth state — and
               * a request nobody has commented on yet is a perfectly ordinary
               * answer, so it gets a sentence rather than a banner.
               */}
              {items.length === 0 ? (
                <p className="text-dense text-text-secondary">
                  No comments yet.
                </p>
              ) : (
                <ul className="flex list-none flex-col gap-3 p-0">
                  {items.map((comment) => (
                    // Keyed by the real id (design.md §6), which closes
                    // frontend-contract.md §6.4: the prototype keyed on the
                    // array index, so inserting at the top would have had
                    // React reuse every row's state under a new comment.
                    <CommentItem key={comment.id} comment={comment} />
                  ))}
                </ul>
              )}

              {/*
               * Only once there is a second page. The dashboard shows its
               * controls unconditionally because a table is a place you page
               * through; a three-comment thread under a disabled Previous
               * button is just noise.
               */}
              {total > data.page_size ? (
                <Pagination
                  total={total}
                  page={data.page}
                  pageSize={data.page_size}
                  shown={items.length}
                  onChange={setPage}
                />
              ) : null}

              {/*
               * Inside the ready branch: the composer exists to add to a
               * visible conversation, and offering a write box under an error
               * banner would accept a comment with nowhere to show it.
               */}
              <CommentComposer
                requestId={requestId}
                isAdmin={isAdmin}
                onPosted={addPosted}
              />
            </div>
          )
        }}
      </AsyncSection>
    </Card>
  )
}

/** One comment: who, when, whether it is internal, and what it says. */
function CommentItem({ comment }: { comment: Comment }) {
  return (
    <li className="flex flex-col gap-1 rounded-card border border-border bg-surface px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-dense font-semibold text-text-primary">
          {fullName(comment.author)}
        </span>
        <Timestamp
          value={comment.created_at}
          withTime
          className="text-meta text-text-secondary"
        />
        {/*
         * CM-2 means a regular user never receives an internal comment at all,
         * so this badge only ever renders for an admin. It is not decoration:
         * an admin who can write internal notes needs to see which of the
         * comments in front of them the requestor cannot read.
         */}
        {comment.is_internal ? (
          <span className="inline-flex items-center rounded-card border border-accent px-2 py-0.5 text-meta font-semibold whitespace-nowrap text-accent">
            Internal
          </span>
        ) : null}
      </div>
      <p className="text-body whitespace-pre-line text-text-primary">
        {comment.body}
      </p>
    </li>
  )
}

// The API-shaped fields this form renders, so a `422` naming anything else
// falls through to the banner rather than into a control that isn't there.
const COMMENT_FIELDS = ['body'] as const

/**
 * Post a comment (CM-5), with the internal checkbox only an admin sees.
 *
 * The checkbox is **absent from the DOM** for a regular user rather than
 * hidden or disabled — same rule the dashboard's Requestor column follows. A
 * control that is only invisible still reads as a control in the accessibility
 * tree and in a screenshot of the markup.
 */
function CommentComposer({
  requestId,
  isAdmin,
  onPosted,
}: {
  requestId: string
  isAdmin: boolean
  onPosted: (comment: Comment) => void
}) {
  const [formError, setFormError] = useState<string | null>(null)
  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<CommentValues>({
    resolver: zodResolver(commentSchema),
    defaultValues: { body: '', is_internal: false },
  })

  const onValidSubmit = async (values: CommentValues) => {
    setFormError(null)
    try {
      // `is_internal` is sent on every post, and for a regular user it is
      // always `false` — the control isn't rendered and the default stands, so
      // the body they send is one CM-7 has no reason to refuse.
      const created = await createComment(requestId, {
        body: values.body,
        is_internal: values.is_internal,
      })
      reset()
      onPosted(created)
    } catch (error) {
      // CM-6's `422` lands inline on `body`; a `403` (CM-7), a `404` (CM-9) or
      // anything else isn't attributable to a field and surfaces as the
      // server's own message in the banner.
      if (!applyFieldErrors(error, setError, COMMENT_FIELDS)) {
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
      {formError !== null ? <ErrorBanner message={formError} /> : null}

      <Field
        label="Add a comment"
        htmlFor="comment-body"
        error={errors.body?.message}
      >
        <Textarea
          id="comment-body"
          aria-invalid={errors.body ? true : undefined}
          {...register('body', { onChange: () => setFormError(null) })}
        />
      </Field>

      {isAdmin ? (
        // Laid out here rather than through Field, which stacks its label
        // above the control — a checkbox wants its label beside it, and this is
        // the app's only one. If a second appears, that is the moment to
        // extract a Checkbox primitive; the same reasoning keeps the
        // dashboard's FilterField local to its page.
        <div className="flex items-center gap-2">
          <input
            id="comment-internal"
            type="checkbox"
            className="size-4 accent-accent"
            {...register('is_internal')}
          />
          <label htmlFor="comment-internal" className="text-dense text-text-primary">
            Internal note — visible to administrators only
          </label>
        </div>
      ) : null}

      {/* Disabled for the duration of the request, not merely after it
          succeeds — against a real endpoint a second click posts the comment
          twice, the same correctness fix T-AUTH-5 and T-SR-1 made to their
          forms. */}
      <Button type="submit" className="self-start" disabled={isSubmitting}>
        {isSubmitting ? 'Posting…' : 'Post comment'}
      </Button>
    </form>
  )
}
