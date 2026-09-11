import {
  createRequestViaApi,
  expect,
  registerViaApi,
  signIn,
  signInViaApi,
  test,
  uniqueTitle,
} from './fixtures'

/**
 * The Service Requests slice's behaviour (T-SR-1), against the real stack.
 *
 * As with the auth specs, these assert what a person gets rather than which
 * functions ran — with one deliberate exception, the status-filter test, where
 * the requirement *is* that the options come from the network.
 *
 * Every test here was verified by removing the thing it names and watching it
 * go red, per backend/CLAUDE.md's rule applied to the frontend: a test never
 * observed to fail is not verified, only written. This project has caught four
 * real defects that way, three of them in tests rather than in application
 * code.
 */

test('a new user sees the empty state, not an empty table', async ({
  page,
  freshUser,
}) => {
  await signIn(page, freshUser)

  // Empty is `ready` with an empty array (lib/async.ts), so what a new user
  // gets is a sentence explaining the emptiness — not a bare table header, and
  // not the error banner that a fourth "empty" union member would invite.
  await expect(
    page.getByText('You haven’t submitted any requests yet.'),
  ).toBeVisible()

  // And the heading tells a regular user whose list this is. SR-2 gives an
  // admin everyone's requests through this same page, which is why the copy
  // can't be a fixed string.
  await expect(page.getByRole('heading', { name: 'My requests' })).toBeVisible()

  // No table at all, rather than a table of nothing.
  await expect(page.getByRole('table')).toHaveCount(0)
})

test('a request submitted through the form appears on the dashboard', async ({
  page,
  freshUser,
}) => {
  await signIn(page, freshUser)

  const title = uniqueTitle('VPN access for contractor')

  await page.getByRole('link', { name: 'New request' }).click()
  await expect(page).toHaveURL('/requests/new')

  await page.getByLabel('Title').fill(title)
  await page
    .getByLabel('Description')
    .fill('Needs VPN access scoped to the project network segment.')
  await page.getByLabel('Priority').click()
  await page.getByRole('option', { name: 'High' }).click()
  await page.getByRole('button', { name: 'Submit request' }).click()

  await expect(page.getByText('Request submitted')).toBeVisible()

  // The point of the test, and the close of frontend-contract.md §8.7: the
  // prototype's submit never touched the list, so "it worked" was a banner and
  // nothing else. SR-15 orders newest first, so it lands at the top.
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('link', { name: title })).toBeVisible()

  // Following it through proves the detail page reads the `:id` it was given
  // rather than always rendering one fixed object (§3.7).
  await page.getByRole('link', { name: title }).click()
  await expect(page.getByRole('heading', { name: title })).toBeVisible()
  await expect(page.getByText('Unassigned')).toBeVisible()
})

test("another user's request is not found, not silently someone else's", async ({
  page,
  request,
  freshUser,
}) => {
  // `freshUser` seeds the *owner* on the API context, which keeps its own
  // cookie jar — so the browser below is a genuinely different session, not
  // the same user viewed twice.
  await signInViaApi(request, freshUser)
  const owned = await createRequestViaApi(request, {
    title: uniqueTitle('Owned by someone else'),
    description: 'Only the requestor and an admin may read this.',
    priority: 'medium',
  })

  const other = await registerViaApi(request)
  await signIn(page, other)
  await page.goto(`/requests/${owned.id}`)

  // SR-12 answers 404, identical to a request that doesn't exist — existence
  // must not leak to someone who can't read it. The UI's job is to say so
  // visibly rather than render whatever it last had.
  await expect(
    page.getByRole('heading', { name: 'Request not found' }),
  ).toBeVisible()
  await expect(page.getByText(owned.title)).toHaveCount(0)
})

test('the status filter offers what /statuses returned, not a hardcoded four', async ({
  page,
  freshUser,
}) => {
  // The one implementation-level assertion in this file, and it is the
  // requirement rather than a shortcut to it: SR-3 answers an unrecognised
  // status name with a 422, so a hardcoded list would become a broken filter
  // the day the seed changes. Serving a deliberately *partial* set is what
  // tells the two apart — a hardcoded array would render all four regardless
  // of what the network said.
  await page.route('**/api/v1/statuses', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            id: '00000000-0000-0000-0000-000000000002',
            name: 'in_progress',
            sort_order: 2,
            is_terminal: false,
          },
        ],
      }),
    })
  })

  await signIn(page, freshUser)
  await page.getByLabel('Status').click()

  await expect(page.getByRole('option', { name: 'In progress' })).toBeVisible()
  // The three the server didn't send. If these were built from a constant in
  // the frontend they would be here regardless.
  await expect(page.getByRole('option', { name: 'Open' })).toHaveCount(0)
  await expect(page.getByRole('option', { name: 'Resolved' })).toHaveCount(0)
  await expect(page.getByRole('option', { name: 'Closed' })).toHaveCount(0)
})

test('a slow /statuses does not blank a request table that already arrived', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)
  const seeded = await createRequestViaApi(request, {
    title: uniqueTitle('Arrived before the filter options'),
    description: 'The list and its filter options are independent resources.',
    priority: 'low',
  })

  // Never answered. The two resources have independent failure modes and must
  // not share a pending flag — a filter dropdown that can't load its options
  // is a degraded control, not a reason to hide the data.
  await page.route('**/api/v1/statuses', () => {
    // Deliberately left hanging; the route is abandoned when the page closes.
  })

  await signIn(page, freshUser)
  await expect(page.getByRole('link', { name: seeded.title })).toBeVisible()
})

/**
 * Long enough that the stale response cannot possibly arrive before the fresh
 * one, so the ordering under test is the one that actually happens.
 */
const STALE_RESPONSE_HOLD_MS = 2000

test('rapid filter changes never leave the table contradicting the controls', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)
  const highPriority = await createRequestViaApi(request, {
    title: uniqueTitle('High priority'),
    description: 'Should be hidden once the filter moves to Low.',
    priority: 'high',
  })
  const lowPriority = await createRequestViaApi(request, {
    title: uniqueTitle('Low priority'),
    description: 'Should be what the table shows at the end.',
    priority: 'low',
  })

  await signIn(page, freshUser)

  // Hold the *response* to the high-priority query, not its request. The
  // ordering is the entire point: both queries go out, the later one answers
  // first, and the earlier one's answer lands afterwards carrying results that
  // contradict the control the user has since changed.
  //
  // The delay is keyed on this handler's own captured URL, per T-DEBT-3's
  // finding — reading a shared mutable counter back after an `await` lets a
  // later request change it mid-handler, so the hold never applies and the
  // test passes without exercising anything.
  await page.route('**/api/v1/service-requests?*', async (route) => {
    const url = route.request().url()
    const response = await route.fetch()
    if (url.includes('priority=high')) {
      await new Promise((resolve) => setTimeout(resolve, STALE_RESPONSE_HOLD_MS))
    }
    await route.fulfill({ response })
  })

  const priorityFilter = page.getByLabel('Priority')

  await priorityFilter.click()
  await page.getByRole('option', { name: 'High' }).click()
  // Straight on to the next filter without waiting — this is the "change a
  // filter twice quickly" case, which is reachable in ordinary use.
  await priorityFilter.click()
  await page.getByRole('option', { name: 'Low' }).click()

  // The low-priority answer is already in by now; the high-priority one is
  // still being held.
  await expect(page.getByRole('link', { name: lowPriority.title })).toBeVisible()

  // Wait out the hold, so a client that failed to invalidate the in-flight
  // result has every chance to overwrite the table with it.
  await page.waitForTimeout(STALE_RESPONSE_HOLD_MS + 1000)

  await expect(page.getByRole('link', { name: lowPriority.title })).toBeVisible()
  await expect(page.getByRole('link', { name: highPriority.title })).toHaveCount(0)
})

test('pagination reports the envelope and page 2 works', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)

  // One more than XC-10's default page size, so there is a second page holding
  // exactly one row — which makes both the "Showing X–Y of N" arithmetic and
  // the Next button's disabled state observable.
  const total = 21
  const marker = uniqueTitle('Paged')
  for (let index = 0; index < total; index += 1) {
    await createRequestViaApi(request, {
      title: `${marker} #${index}`,
      description: 'Seeded to push the list past one page.',
      priority: 'medium',
    })
  }

  await signIn(page, freshUser)

  await expect(page.getByText(`Showing 1–20 of ${total}`)).toBeVisible()
  await expect(page.getByRole('row')).toHaveCount(21) // 20 rows plus the header
  await expect(page.getByRole('button', { name: 'Previous' })).toBeDisabled()

  await page.getByRole('button', { name: 'Next' }).click()

  // Without these controls a user past 20 requests sees the first page and
  // nothing at all indicating the rest exist — the list simply stops.
  await expect(page.getByText(`Showing 21–${total} of ${total}`)).toBeVisible()
  await expect(page.getByRole('row')).toHaveCount(2)
  await expect(page.getByRole('button', { name: 'Next' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Previous' })).toBeEnabled()
})
