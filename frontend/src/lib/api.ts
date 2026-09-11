/**
 * The one sanctioned fetch client (T-AUTH-4; frontend/CLAUDE.md, "API client
 * conventions"). Nothing outside this file calls `fetch` — what is centralised
 * here is the cross-cutting behaviour every endpoint needs, which is exactly
 * what splitting this per resource would force us to re-implement per file:
 *
 * - `credentials: 'include'` on every call. The session is two httpOnly
 *   cookies (design.md §1) that the page can never read, so this flag is the
 *   whole of "being signed in" as far as the client is concerned.
 * - `X-Requested-With` on every state-changing call (XC-9).
 * - One silent refresh-and-retry on a `401` (design.md §1, AUTH-9).
 * - One typed error shape, so callers branch on `error.code` and never on
 *   `message` text — messages can be reworded, codes are the contract.
 *
 * Response bodies are typed, not validated: each call's type parameter asserts
 * that the backend keeps design.md's contract. Add runtime parsing here only
 * if a real mismatch turns up, not pre-emptively — zod is for form input,
 * where the data genuinely is untrusted.
 */

// XC-1 puts every endpoint under `/api/v1`; VITE_API_URL carries only the
// origin (see .env.example), because in dev the API is on :8000 and Vite on
// :5173. Unset, this falls back to a same-origin relative path — what a
// deployment serving both from one host would want.
const API_BASE_URL = `${import.meta.env.VITE_API_URL ?? ''}/api/v1`

/** design.md §1's error table, plus the two failures that never reach it. */
export type ApiErrorCode =
  | 'BAD_REQUEST'
  | 'UNAUTHENTICATED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'VALIDATION_ERROR'
  | 'INTERNAL_ERROR'
  // Client-side only: the request never got an answer (offline, DNS, or a
  // CORS rejection, which the browser reports to script as a plain failure).
  | 'NETWORK_ERROR'
  // Client-side only: something answered, but not with the error envelope —
  // a proxy's HTML error page, say.
  | 'MALFORMED_RESPONSE'

/** XC-4's `fields` map. Present on `VALIDATION_ERROR` only (design.md §1). */
export type FieldErrors = Record<string, string[]>

const UNEXPECTED_RESPONSE_MESSAGE = 'The server returned an unexpected response.'
const NETWORK_ERROR_MESSAGE =
  'Could not reach the server. Check your connection and try again.'

/**
 * Every failure this module throws, success being the only other outcome.
 *
 * `status` is the HTTP status, or `0` for the two client-side codes above,
 * where there is no meaningful one — branch on `code`, not on `status`.
 */
export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number
  readonly fields?: FieldErrors

  constructor(
    code: ApiErrorCode,
    message: string,
    status: number,
    fields?: FieldErrors,
    options?: ErrorOptions,
  ) {
    super(message, options)
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.fields = fields
  }
}

/** For `catch (error)` blocks, where TypeScript hands back `unknown`. */
export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError
}

// --- Response handling -------------------------------------------------------

// Used only when a response is *not* the envelope; the backend's own
// `_STATUS_TO_CODE` is the shape being mirrored.
const STATUS_CODES: Record<number, ApiErrorCode> = {
  400: 'BAD_REQUEST',
  401: 'UNAUTHENTICATED',
  403: 'FORBIDDEN',
  404: 'NOT_FOUND',
  409: 'CONFLICT',
  422: 'VALIDATION_ERROR',
}

function codeForStatus(status: number): ApiErrorCode {
  return STATUS_CODES[status] ?? (status >= 500 ? 'INTERNAL_ERROR' : 'BAD_REQUEST')
}

interface ErrorEnvelope {
  code: string
  message: string
  fields?: FieldErrors
}

function readEnvelope(text: string): ErrorEnvelope | null {
  let body: unknown
  try {
    body = JSON.parse(text)
  } catch {
    return null
  }
  if (typeof body !== 'object' || body === null || !('error' in body)) return null

  const error = (body as { error: unknown }).error
  if (typeof error !== 'object' || error === null) return null

  const { code, message, fields } = error as Record<string, unknown>
  if (typeof code !== 'string' || typeof message !== 'string') return null

  return {
    code,
    message,
    fields:
      typeof fields === 'object' && fields !== null
        ? (fields as FieldErrors)
        : undefined,
  }
}

function errorFrom(status: number, text: string): ApiError {
  const envelope = readEnvelope(text)
  if (envelope === null) {
    // Nothing usable came back, but a caller still has to be able to branch on
    // a code, so derive the closest one from the status rather than handing
    // back a parse failure.
    return new ApiError(codeForStatus(status), UNEXPECTED_RESPONSE_MESSAGE, status)
  }
  // The backend's `code` set is closed (errors.py) — an unknown string here
  // would mean the two have already drifted, which no cast can fix.
  return new ApiError(
    envelope.code as ApiErrorCode,
    envelope.message,
    status,
    envelope.fields,
  )
}

/**
 * Read a response as either its parsed body or an `ApiError`.
 *
 * Read as text first, then parsed: `response.json()` throws on an empty or
 * non-JSON body, and a thrown `SyntaxError` from inside the client is exactly
 * what callers must never have to handle.
 */
async function toResult<T>(response: Response): Promise<T> {
  let text: string
  try {
    text = response.status === 204 ? '' : await response.text()
  } catch (cause) {
    // The response started and then the connection died mid-body.
    throw new ApiError('NETWORK_ERROR', NETWORK_ERROR_MESSAGE, response.status, undefined, {
      cause,
    })
  }

  if (!response.ok) throw errorFrom(response.status, text)

  // `204` (logout) and any other empty success body resolve as `undefined`;
  // those callers declare `void` and never look at the value.
  if (text === '') return undefined as T

  try {
    return JSON.parse(text) as T
  } catch (cause) {
    throw new ApiError(
      'MALFORMED_RESPONSE',
      UNEXPECTED_RESPONSE_MESSAGE,
      response.status,
      undefined,
      { cause },
    )
  }
}

// --- Requests ----------------------------------------------------------------

type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE'

interface RequestOptions {
  method?: HttpMethod
  body?: unknown
  /** For calls a component starts and may need to drop, e.g. on unmount. */
  signal?: AbortSignal
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const method = options.method ?? 'GET'
  const headers: Record<string, string> = { Accept: 'application/json' }

  if (method !== 'GET') {
    // XC-9. Presence is the entire check — a cross-site form post cannot set a
    // custom header at all, which is what makes this a CSRF defence; the value
    // is never read server-side, so this string carries no meaning.
    headers['X-Requested-With'] = 'XMLHttpRequest'
  }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'

  try {
    return await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      credentials: 'include',
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (cause) {
    // An abort is the caller's own doing, not a failure — it propagates as the
    // DOMException it is, so an unmount doesn't surface as a network banner.
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError('NETWORK_ERROR', NETWORK_ERROR_MESSAGE, 0, undefined, { cause })
  }
}

const REFRESH_PATH = '/auth/refresh'
const LOGIN_PATH = '/auth/login'

// A `401` from these two is the answer to the question asked, not a symptom of
// an expired access token: `/auth/login` reads no cookie at all (a refresh
// cannot change whether a password is right), and `/auth/refresh` *is* the
// recovery path, so retrying it through itself would be a loop.
const NO_REFRESH_RETRY = new Set<string>([LOGIN_PATH, REFRESH_PATH])

let refreshInFlight: Promise<boolean> | null = null

// Bumped once per successful refresh. A call captures this before it is sent,
// so afterwards it can tell "nobody has refreshed since I started" from "the
// token I was sent with has already been replaced".
let sessionGeneration = 0

/**
 * One `POST /auth/refresh` per expired access token, shared by every caller.
 *
 * The sharing is a correctness requirement, not an optimisation: refresh
 * tokens are single-use and rotated (design.md §1), and AUTH-11 reads a
 * *replayed* one as theft and revokes every live token for that user. Two
 * calls 401-ing at once would send the same cookie twice, and the second would
 * sign the user out everywhere — a page that fires two requests on mount is
 * enough to trigger it.
 *
 * The generation check covers the near miss the in-flight promise alone does
 * not: a call whose `401` lands just *after* a refresh completed. Its cookie
 * was already stale when it was sent, so a second rotation would be pointless
 * — it only needs the retry.
 */
function refreshSession(generation: number): Promise<boolean> {
  if (generation !== sessionGeneration) return Promise.resolve(true)

  if (refreshInFlight === null) {
    refreshInFlight = attemptRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

async function attemptRefresh(): Promise<boolean> {
  try {
    await request<SessionUser>(REFRESH_PATH, { method: 'POST' })
    sessionGeneration += 1
    return true
  } catch {
    // Any failure means the same thing to the caller waiting on this: there is
    // no usable session, so their original `401` stands. Which failure it was
    // changes nothing they can do about it.
    return false
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  // Read before the call goes out: which token this request carried is what
  // decides whether a `401` on the way back is worth a refresh.
  const generation = sessionGeneration
  const response = await send(path, options)

  const endpoint = path.split('?')[0]
  if (response.status !== 401 || NO_REFRESH_RETRY.has(endpoint)) {
    return toResult<T>(response)
  }

  if (!(await refreshSession(generation))) {
    // Refresh failed too. The caller gets the `401` from the call they
    // actually made, not the refresh's — that one is this module's business.
    return toResult<T>(response)
  }

  // One retry, whatever it answers. A second `401` here is a real answer (the
  // route may need a role the session doesn't have), not another stale token.
  return toResult<T>(await send(path, options))
}

// --- Auth (design.md §2) -----------------------------------------------------

export type UserRole = 'user' | 'admin'

/** What `login`, `refresh` and `/auth/me` all return — one "current user". */
export interface SessionUser {
  id: string
  first_name: string
  last_name: string
  role: UserRole
}

/**
 * `POST /auth/register`'s `201` body. Deliberately not `extends SessionUser`,
 * mirroring the backend model's own reasoning: the two overlap by coincidence
 * of what registration echoes back, and tying them together would propagate a
 * later change in the session shape into the registration contract.
 */
export interface RegisteredUser {
  id: string
  first_name: string
  last_name: string
  email: string
  role: UserRole
  created_at: string
}

/**
 * Request bodies keep the wire's snake_case (frontend/CLAUDE.md, Naming
 * exception) — there is no translation layer at this boundary.
 */
export interface RegisterInput {
  first_name: string
  last_name: string
  email: string
  password: string
}

export interface LoginInput {
  email: string
  password: string
}

/** AUTH-1. Does not sign the new user in — no cookies are set (design.md §2). */
export function register(input: RegisterInput): Promise<RegisteredUser> {
  return request<RegisteredUser>('/auth/register', { method: 'POST', body: input })
}

/** AUTH-6. On success the browser holds both session cookies. */
export function login(input: LoginInput): Promise<SessionUser> {
  return request<SessionUser>(LOGIN_PATH, { method: 'POST', body: input })
}

/**
 * AUTH-14 — the session bootstrap: httpOnly cookies are invisible to script,
 * so this call is how a freshly loaded page finds out whether it has a
 * session. A `401` here means signed out (AUTH-15: `/me` never refreshes
 * server-side — the retry above is what covers a merely expired access token).
 */
export function getMe(signal?: AbortSignal): Promise<SessionUser> {
  return request<SessionUser>('/auth/me', { signal })
}

/** AUTH-12/AUTH-13. Idempotent and always `204`, session or not. */
export function logout(): Promise<void> {
  return request<void>('/auth/logout', { method: 'POST' })
}

// --- Shared shapes (design.md §1) --------------------------------------------

/**
 * The two closed vocabularies the API uses as plain strings, declared here
 * rather than next to the pills that colour them.
 *
 * Both are wire values, so this module owns them and the presentation layer
 * imports them — the reverse would make `api.ts` depend on a component, and
 * two independent copies are how frontend-contract.md §9-#8's
 * two-non-matching-status-enums problem happened in the first place.
 */
export type Priority = 'low' | 'medium' | 'high'

/** The four seeded `statuses` rows (design.md §3). `draft` is not one of them. */
export type StatusName = 'open' | 'in_progress' | 'resolved' | 'closed'

/** design.md §1's `Status` — the whole row, not just its name. */
export interface Status {
  id: string
  name: StatusName
  sort_order: number
  is_terminal: boolean
}

/**
 * design.md §1's `UserSummary` — a reference for display, deliberately not the
 * full user (no email, no timestamps).
 */
export interface UserSummary {
  id: string
  first_name: string
  last_name: string
  role: UserRole
}

/** XC-10's list envelope. `total` is what *this caller* can see, not the table. */
export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

// --- Statuses (design.md §3) -------------------------------------------------

/**
 * ST-1/ST-2. Public — no session needed, and not paginated: four rows, always.
 *
 * This is the authority on which status names exist. A hardcoded list in the
 * frontend would be free to drift from the seed, and SR-3 answers an
 * unrecognised name with a `422` rather than an empty list, so the drift would
 * surface as a filter that errors rather than one that finds nothing.
 */
export function getStatuses(signal?: AbortSignal): Promise<{ items: Status[] }> {
  return request<{ items: Status[] }>('/statuses', { signal })
}

// --- Service requests (design.md §4) -----------------------------------------

/** One shape for list and detail alike (design.md §0 decision 2). */
export interface ServiceRequest {
  id: string
  title: string
  request_type: string
  priority: Priority
  status: Status
  requestor: UserSummary
  /**
   * Always `null` this phase — there is no assignment path and `PATCH` is
   * deferred (design.md §7). Optional because the column is nullable, not
   * because anything populates it yet.
   */
  assignee: UserSummary | null
  created_at: string
  updated_at: string
  description: string
}

/** `GET /service-requests`' query string (SR-3, SR-4, XC-10). */
export interface ServiceRequestQuery {
  page?: number
  page_size?: number
  /** A `name` from `getStatuses`, never a string typed out here (SR-3). */
  status?: StatusName
  priority?: Priority
}

function queryString(query: ServiceRequestQuery): string {
  const params = new URLSearchParams()
  // Omitted rather than sent empty: the backend reads "absent" as "no filter",
  // and `?status=` would reach `_resolve_status_filter` as a name to look up.
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value))
  }
  const rendered = params.toString()
  return rendered === '' ? '' : `?${rendered}`
}

/** SR-1 through SR-5, SR-15. Scoping is the server's (owner, or all for admin). */
export function getServiceRequests(
  query: ServiceRequestQuery = {},
  signal?: AbortSignal,
): Promise<Page<ServiceRequest>> {
  return request<Page<ServiceRequest>>(`/service-requests${queryString(query)}`, {
    signal,
  })
}

/**
 * SR-6's body. The three fields SR-10/XC-8 name as server-controlled
 * (`request_type`, `requestor_id`, `current_status_id`) are absent by
 * construction, so there is nothing for a caller to supply and have ignored.
 */
export interface CreateServiceRequestInput {
  title: string
  description: string
  priority: Priority
}

/** SR-6. Also writes the request's first `status_history` row (SR-14). */
export function createServiceRequest(
  input: CreateServiceRequestInput,
): Promise<ServiceRequest> {
  return request<ServiceRequest>('/service-requests', { method: 'POST', body: input })
}

/**
 * SR-11 through SR-13. A malformed id, a missing row and someone else's
 * request are one answer — `404`/`NOT_FOUND` — so a caller cannot tell them
 * apart, and neither should the UI try to.
 */
export function getServiceRequest(
  id: string,
  signal?: AbortSignal,
): Promise<ServiceRequest> {
  return request<ServiceRequest>(`/service-requests/${encodeURIComponent(id)}`, {
    signal,
  })
}
