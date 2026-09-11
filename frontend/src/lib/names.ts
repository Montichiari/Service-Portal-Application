/**
 * The one place a `UserSummary` becomes a name on screen.
 *
 * design.md §0 decision 4: `requestor` and `assignee` arrive as structured
 * objects, never as pre-formatted display strings like the prototype's
 * 'Priya Nair — IT Service Desk'. Joining them is the frontend's job, and it
 * lives here for the same reason datetime.ts exists — done in two places, the
 * two drift, and the inconsistency the structured objects were meant to end
 * comes back in a new costume.
 *
 * Extracted in T-DEBT-5, when the admin Requestor column made the dashboard the
 * second page needing it; it was local to RequestDetailsPage until then.
 */

import type { UserSummary } from '@/lib/api'

/**
 * `first_name last_name`.
 *
 * Takes a non-null `UserSummary` only. `assignee` is `null` on every request
 * this phase (design.md §7), but what to show in its place is the caller's
 * call, not this module's — RequestDetailsPage's 'Unassigned' is a sentence
 * about that page's layout, and a second caller could want something else.
 */
export function fullName(user: UserSummary): string {
  return `${user.first_name} ${user.last_name}`
}
