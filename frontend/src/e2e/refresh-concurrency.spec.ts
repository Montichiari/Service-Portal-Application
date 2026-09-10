import { expect, signIn, test } from './fixtures'

/**
 * `api.ts`'s refresh rule (T-AUTH-4), the riskiest logic in the slice and the
 * one a well-meaning refactor would simplify straight back into a bug.
 *
 * The guarantee is a network pattern, so this asserts on requests rather than
 * on what the page shows — the exception frontend/CLAUDE.md's Testing section
 * carves out of "test behaviour, not implementation". Concurrent `401`s must
 * produce **exactly one** `/auth/refresh`: refresh tokens are single-use and
 * rotated (AUTH-9), and presenting a rotated one reads as theft and revokes
 * every live token for that user (AUTH-11). A redundant refresh is one
 * arrival-order shift away from signing someone out of everything for doing
 * nothing wrong.
 */

const ACCESS_COOKIE = 'access_token'
const ME_ENDPOINT = '**/api/v1/auth/me'

/**
 * Long enough that the first call's refresh has certainly finished — it is one
 * round trip, tens of milliseconds — before the second call's `401` lands.
 */
const HOLD_RESPONSE_MS = 800

test('concurrent 401s produce exactly one refresh', async ({
  page,
  context,
  freshUser,
}) => {
  await signIn(page, freshUser)

  // Expire the session the only way a test can without waiting out AUTH-6's
  // one-hour TTL: drop the access cookie and keep the refresh cookie. Every
  // call from here answers 401 exactly as it would after a natural expiry.
  await context.clearCookies({ name: ACCESS_COOKIE })

  // Hold the *response* to the second call rather than delaying its request.
  // That ordering is the entire point: both calls are sent against the same
  // (now missing) token, but the second one's 401 arrives after the first
  // call's refresh has already replaced it. A shared in-flight promise does
  // not cover that case — by then the promise has settled and cleared, so a
  // client without the session-generation check starts a second refresh.
  //
  // The pair under test are requests 1 and 2 by construction: a retry cannot
  // be issued until a response has come back, so it is always later.
  let meCalls = 0
  await page.route(ME_ENDPOINT, async (route) => {
    // Captured at entry rather than read back off the shared counter while
    // awaiting. Keying the delay on the mutable value lets a later request
    // increment it mid-handler, so nothing is held, both 401s arrive together,
    // and the in-flight promise alone dedupes them — the test then passes
    // without testing anything. Found by removing the guard and watching this
    // stay green.
    const call = (meCalls += 1)
    const response = await route.fetch()
    if (call === 2) {
      await new Promise((resolve) => setTimeout(resolve, HOLD_RESPONSE_MS))
    }
    await route.fulfill({ response })
  })

  const refreshCalls: string[] = []
  page.on('request', (request) => {
    if (request.url().includes('/auth/refresh')) refreshCalls.push(request.url())
  })

  // Straight at the module the app itself uses. No page in the app fires two
  // calls at once yet, and inventing one to test this would be testing the
  // scaffolding instead of the client.
  const outcomes = await page.evaluate(async () => {
    // A URL the dev server resolves, not a module path this project compiles —
    // held in a variable so TypeScript doesn't try to resolve it from here.
    // Same URL the app imports, so this is the app's own client instance.
    const moduleUrl = '/src/lib/api.ts'
    const api = (await import(moduleUrl)) as { getMe: () => Promise<unknown> }
    const settled = await Promise.allSettled([api.getMe(), api.getMe()])
    return settled.map((result) => result.status)
  })

  // Both callers get their answer — the retry is transparent to them, which is
  // the behaviour the refresh exists to provide.
  expect(outcomes).toEqual(['fulfilled', 'fulfilled'])

  // Two calls, each retried once. If this is 2 or 3, the delayed call never
  // 401'd and the assertion below would be proving nothing.
  expect(meCalls, 'two calls, each retried once').toBe(4)

  // And it cost exactly one rotation.
  expect(refreshCalls).toHaveLength(1)
})
