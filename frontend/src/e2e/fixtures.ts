import { execFileSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test as base, expect, type APIRequestContext, type Page } from '@playwright/test'

/**
 * Shared setup for the e2e suite (T-DEBT-3).
 *
 * Every test seeds its own user. Nothing here depends on a row someone
 * created by hand once — that kind of fixture rots silently, and the first
 * symptom is a failure that looks like a bug in the code under test
 * (frontend/CLAUDE.md, Testing).
 */

/** The backend origin — the same default the app's `.env` points `VITE_API_URL` at. */
export const API_BASE_URL = process.env.E2E_API_URL ?? 'http://localhost:8000'

/** Clears AUTH-3's 12-character minimum and is otherwise unremarkable. */
export const TEST_PASSWORD = 'playwright-e2e-password'

export interface TestUser {
  email: string
  password: string
  first_name: string
  last_name: string
}

/**
 * A fresh address per call. `@example.com`, not `@example.test`, which
 * `email-validator` rejects as a reserved TLD (backend/CLAUDE.md).
 */
export function uniqueEmail(): string {
  const suffix = Math.random().toString(36).slice(2, 8)
  return `e2e.${Date.now()}.${suffix}@example.com`
}

/**
 * Register a user straight against the API.
 *
 * Deliberately not through the register form: only the journey test is about
 * that form, and routing every other test's setup through it would make an
 * unrelated markup change fail the whole suite. Registration sets no cookies
 * (design.md §2), so this leaves the browser signed out.
 */
export async function registerViaApi(
  request: APIRequestContext,
  // Overridable because a test that needs to tell two users apart on screen
  // needs them to have different names — the shared default would make the
  // T-CM-1 requestor-column test pass whichever name it rendered.
  name: { first_name: string; last_name: string } = {
    first_name: 'Playwright',
    last_name: 'Runner',
  },
): Promise<TestUser> {
  const user: TestUser = {
    email: uniqueEmail(),
    password: TEST_PASSWORD,
    ...name,
  }

  const response = await request.post(`${API_BASE_URL}/api/v1/auth/register`, {
    // XC-9: any non-GET without this header is refused 403 before the route
    // runs. The value is never read — presence is the whole check.
    headers: { 'X-Requested-With': 'playwright' },
    data: user,
  })
  expect(response.status(), `registering ${user.email}`).toBe(201)

  return user
}

/** Sign in through the real form, the way a person does. */
export async function signIn(page: Page, user: TestUser): Promise<void> {
  await page.goto('/login')
  await page.getByLabel('Email').fill(user.email)
  await page.getByLabel('Password').fill(user.password)
  await page.getByRole('button', { name: 'Sign in' }).click()

  // The post-login destination is the dashboard, and the account block only
  // renders for a session the app actually holds — so this waits for a real
  // signed-in state, not merely for a URL to change.
  await expect(page).toHaveURL('/')
  await expect(page.getByText(signedInAs(user))).toBeVisible()
}

/** What AppShell prints for a signed-in user. */
export function signedInAs(user: TestUser): string {
  return `Signed in as ${user.first_name} ${user.last_name}`
}

/**
 * Sign in on an `APIRequestContext` so it can make authenticated calls.
 *
 * This context's cookie jar is its own — separate from any `page`'s — which is
 * what lets one test seed data as one user while the browser is signed in as
 * another. That separation is the whole mechanism behind the SR-12 test.
 */
export async function signInViaApi(
  request: APIRequestContext,
  user: TestUser,
): Promise<void> {
  const response = await request.post(`${API_BASE_URL}/api/v1/auth/login`, {
    headers: { 'X-Requested-With': 'playwright' },
    data: { email: user.email, password: user.password },
  })
  expect(response.status(), `signing in ${user.email}`).toBe(200)
}

export interface SeededRequest {
  id: string
  title: string
}

/**
 * File a request straight against the API, as whoever `request` is signed in
 * as.
 *
 * Not through the submit form: only the create-then-see test is about that
 * form, and routing every other test's setup through it would make an
 * unrelated markup change fail tests that have nothing to do with it — the
 * same reasoning as `registerViaApi`.
 */
export async function createRequestViaApi(
  request: APIRequestContext,
  input: { title: string; description: string; priority: 'low' | 'medium' | 'high' },
): Promise<SeededRequest> {
  const response = await request.post(`${API_BASE_URL}/api/v1/service-requests`, {
    headers: { 'X-Requested-With': 'playwright' },
    data: input,
  })
  expect(response.status(), `creating ${input.title}`).toBe(201)
  return (await response.json()) as SeededRequest
}

/**
 * Transition a request straight against the API, as whoever `request` is signed
 * in as — which SC-4 requires to be an admin.
 *
 * The status is named rather than identified: ids are seeded per database, so a
 * test that hardcoded one would pass only against the machine it was written
 * on. `GET /statuses` is the authority on the mapping (ST-1 needs no session
 * for it), which is the same reason the dashboard fetches its filter options
 * rather than typing out four strings.
 */
export async function changeStatusViaApi(
  request: APIRequestContext,
  requestId: string,
  statusName: 'open' | 'in_progress' | 'resolved' | 'closed',
  note?: string,
): Promise<void> {
  const statuses = await request.get(`${API_BASE_URL}/api/v1/statuses`)
  expect(statuses.status(), 'listing statuses').toBe(200)
  const { items } = (await statuses.json()) as { items: { id: string; name: string }[] }

  const target = items.find((status) => status.name === statusName)
  // A seed that no longer carries this name would otherwise surface as a 422
  // from the POST below, which reads like a broken endpoint rather than a
  // broken fixture.
  expect(target, `no seeded status named ${statusName}`).toBeDefined()

  const response = await request.post(
    `${API_BASE_URL}/api/v1/service-requests/${requestId}/status-changes`,
    {
      headers: { 'X-Requested-With': 'playwright' },
      data: { status_id: target!.id, note },
    },
  )
  expect(response.status(), `moving ${requestId} to ${statusName}`).toBe(201)
}

/** Repo root, from this file — where docker-compose.yml lives. */
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')

/**
 * Promote a registered user to `admin`, by `UPDATE` against the dev database.
 *
 * There is no admin-promotion endpoint and deliberately none: AUTH-4 ignores a
 * `role` in the register body precisely so the API cannot mint an admin, and
 * `deps.py` reads `role` off the user row on every request rather than from the
 * token's claim — which is what makes an out-of-band `UPDATE` the documented
 * way promotion happens, and what makes it take effect on the caller's very
 * next request.
 *
 * Call this **before** signing the browser in: `AuthContext` caches what login
 * returned, so a promotion afterwards leaves the UI reading `user` until the
 * next `GET /auth/me`.
 *
 * SR-2, CM-3 and CM-8 all behave differently for an admin, and T-DEBT-5 checked
 * the first of them by hand against a manually promoted account. Hand-promotion
 * is exactly the hand-maintained fixture this suite avoids, so it is automated
 * here instead.
 */
export function promoteToAdmin(user: TestUser): void {
  let output: string
  try {
    output = execFileSync(
      'docker',
      [
        'compose',
        'exec',
        '-T',
        'db',
        'psql',
        '-U',
        'portal',
        '-d',
        'portal',
        '-v',
        'ON_ERROR_STOP=1',
        '-v',
        `email=${user.email}`,
      ],
      {
        cwd: REPO_ROOT,
        encoding: 'utf8',
        stdio: 'pipe',
        // Fed on stdin rather than through `-c`: psql interpolates `:'email'`
        // — its own quoting of a variable, so the address is never spliced
        // into SQL text by us — only when reading a script, not a `-c` string.
        input: "UPDATE users SET role = 'admin' WHERE email = :'email';\n",
      },
    )
  } catch (cause) {
    throw new Error(
      `Could not promote ${user.email} to admin. This uses the docker-compose ` +
        `Postgres from the repo root (docker compose exec db psql …) — the same ` +
        `database backend/.env points DATABASE_URL at. Is the db service up?`,
      { cause },
    )
  }

  // `UPDATE 0` is a successful command that changed nothing — which would leave
  // a "regular user sees the admin view" test passing for the wrong reason.
  expect(output, `promoting ${user.email}`).toContain('UPDATE 1')
}

/** A title nothing else in the database will share, so a locator can't collide. */
export function uniqueTitle(prefix: string): string {
  const suffix = Math.random().toString(36).slice(2, 8)
  return `${prefix} ${Date.now()}-${suffix}`
}

/**
 * A test that gets its own registered, not-yet-signed-in user.
 *
 * Playwright names a fixture's second parameter `use` by convention; it is
 * positional, so this calls it `provide` instead — `use` inside an arrow
 * function reads as React's `use` hook to the linter, and renaming beats
 * suppressing a rule that is right to be suspicious in every other file.
 */
export const test = base.extend<{ freshUser: TestUser }>({
  freshUser: async ({ request }, provide) => {
    await provide(await registerViaApi(request))
  },
})

export { expect }
