import { API_BASE_URL } from './fixtures'

/**
 * Fail fast, and legibly, when the backend isn't running.
 *
 * Without this the whole suite dies in `beforeEach` on a connection refused
 * from a URL the reader has to decode — the same failure a genuinely broken
 * auth flow produces. Naming the cause up front costs one request.
 */
export default async function globalSetup() {
  const probe = `${API_BASE_URL}/api/v1/auth/me`

  let response: Response
  try {
    response = await fetch(probe)
  } catch (cause) {
    throw new Error(
      `Backend not reachable at ${API_BASE_URL}. Start it (uvicorn app.main:app --reload, ` +
        `with Postgres up) before running the e2e suite, or point E2E_API_URL elsewhere.`,
      { cause },
    )
  }

  // Signed out, `/auth/me` answers 401 (AUTH-15) — that *is* the healthy
  // answer here. Anything else means something is listening that isn't this
  // API, which is worth saying before the tests blame the frontend.
  if (response.status !== 401 && response.status !== 200) {
    throw new Error(
      `Unexpected ${response.status} from ${probe} — expected 401 (signed out) or 200. ` +
        `Is something other than the Service Portal API on ${API_BASE_URL}?`,
    )
  }
}
