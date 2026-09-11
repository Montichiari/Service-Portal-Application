/**
 * The one date-formatting module (T-SR-1).
 *
 * XC-2 replaced the prototype's three inconsistent pre-formatted strings
 * ('2h ago', '4 Sep 2026', '4 Sep 2026, 14:10') with one machine-readable
 * format: ISO 8601, UTC, explicit offset. Turning that into something a person
 * reads is entirely a frontend concern, done at render time — and done in one
 * place, or the inconsistency comes straight back in a new costume.
 *
 * `Intl.DateTimeFormat` covers this; no date library is added. The locale is
 * left `undefined` on purpose — that resolves to the viewer's own, which is
 * the right answer for a timestamp rendered in their browser, and pinning
 * 'en-GB' here would be a hardcoded assumption about who is looking.
 *
 * Formatters are built once at module scope rather than per call: constructing
 * one is the expensive part of `Intl`, and a table of twenty rows would
 * otherwise build twenty.
 */

const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' })

const DATE_TIME_FORMAT = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
})

/**
 * What to show when a timestamp cannot be read at all.
 *
 * `Intl` throws a `RangeError` on an invalid date rather than returning
 * anything, so an unexpected string would take down the render of the row it
 * appears in. A column reading '—' is a visible oddity; a blank page is a
 * mystery.
 */
const UNKNOWN_DATE = '—'

function parse(iso: string): Date | null {
  const value = new Date(iso)
  return Number.isNaN(value.getTime()) ? null : value
}

/** Date only — for a column where the time of day is noise. */
export function formatDate(iso: string): string {
  const value = parse(iso)
  return value === null ? UNKNOWN_DATE : DATE_FORMAT.format(value)
}

/** Date and time — for a single timestamp the reader is looking straight at. */
export function formatDateTime(iso: string): string {
  const value = parse(iso)
  return value === null ? UNKNOWN_DATE : DATE_TIME_FORMAT.format(value)
}
