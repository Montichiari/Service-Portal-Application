import {
  changeStatusViaApi,
  createRequestViaApi,
  expect,
  promoteToAdmin,
  registerViaApi,
  signIn,
  signInViaApi,
  test,
  uniqueTitle,
} from './fixtures'

/**
 * The Status history slice's behaviour (T-SC-1), against the real stack.
 *
 * The page's whole job is a merge that only exists on this side of the wire:
 * SC-3 has the API report transitions that happened and nothing else, so
 * "Resolved, not yet reached" is a sentence no response contains and only the
 * rendered page can be asked about.
 *
 * Every test here was verified by removing the thing it names and watching it
 * go red, per backend/CLAUDE.md's rule applied to the frontend — a test never
 * observed to fail is not verified, only written.
 */

/** The four seeded statuses in `sort_order` (ST-2), as the pills label them. */
const STEP_LABELS = ['Open', 'In progress', 'Resolved', 'Closed']

/** One stepper row, addressed by the status it stands for. */
const stepFor = (page: Parameters<typeof signIn>[0], label: string) =>
  page.getByRole('listitem').filter({ hasText: label })

test('the stepper fills reached statuses and leaves the rest hollow', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)
  const owned = await createRequestViaApi(request, {
    title: uniqueTitle('Monitor flickers on wake'),
    description: 'The second display comes back with a visible flicker.',
    priority: 'medium',
  })

  // SR-14 already wrote the `open` transition inside the create, so one more
  // makes the two this criterion asks for. Nothing synthesises the first step.
  const admin = await registerViaApi(request, {
    first_name: 'Sam',
    last_name: 'Supervisor',
  })
  promoteToAdmin(admin)
  await signInViaApi(request, admin)
  await changeStatusViaApi(request, owned.id, 'in_progress', 'Bench test booked.')

  await signIn(page, freshUser)
  await page.goto(`/requests/${owned.id}/status`)

  // The heading is the request's real title, not the id alone — T-SR-1 dropped
  // it while the timeline below it was still invented.
  await expect(page.getByRole('heading', { name: owned.title })).toBeVisible()

  // Every seeded status is a step, in `sort_order` — the un-reached ones come
  // from `GET /statuses`, since the history endpoint never mentions them.
  await expect(page.getByRole('listitem')).toHaveText(
    STEP_LABELS.map((label) => new RegExp(label)),
  )

  // Reached steps carry the real transition; un-reached ones say so in words
  // rather than only through a dot the screen reader can't see.
  await expect(stepFor(page, 'Open')).not.toContainText('Not yet reached')
  await expect(stepFor(page, 'In progress')).toContainText('Bench test booked.')
  await expect(stepFor(page, 'In progress')).not.toContainText('Not yet reached')
  await expect(stepFor(page, 'Resolved')).toContainText('Not yet reached')
  await expect(stepFor(page, 'Closed')).toContainText('Not yet reached')

  // SC-3: the two steps that are filled are filled by rows that exist. A third
  // reached step here would mean something invented one.
  await expect(page.getByText('Not yet reached')).toHaveCount(2)
})

test('a regular user gets no status-change control at all', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)
  const owned = await createRequestViaApi(request, {
    title: uniqueTitle('Password reset for shared mailbox'),
    description: 'The shared mailbox credentials expired over the weekend.',
    priority: 'low',
  })

  await signIn(page, freshUser)
  await page.goto(`/requests/${owned.id}/status`)

  // They can read their own request's history — SC-1 gives it to anyone who can
  // see the request, so this is not an empty page they were denied.
  await expect(stepFor(page, 'Open')).toBeVisible()

  // Absent from the DOM, not hidden or disabled. SC-4 answers a user's POST
  // with a 403 regardless, so this is about not offering a control whose only
  // possible outcome is a rejection.
  await expect(page.getByLabel('New status')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Update status' })).toHaveCount(0)
})

test('posting a status change updates the stepper without a page reload', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)
  const owned = await createRequestViaApi(request, {
    title: uniqueTitle('Docking station unrecognised'),
    description: 'The dock powers the laptop but no peripherals appear.',
    priority: 'high',
  })

  const admin = await registerViaApi(request, {
    first_name: 'Sam',
    last_name: 'Supervisor',
  })
  promoteToAdmin(admin)

  await signIn(page, admin)
  await page.goto(`/requests/${owned.id}/status`)

  await expect(stepFor(page, 'Resolved')).toContainText('Not yet reached')

  // Survives anything short of a document navigation, so it is what tells an
  // in-place update from a reload that happens to end up looking the same —
  // asserting the step became filled cannot distinguish the two (T-CM-1).
  await page.evaluate(() => {
    ;(window as unknown as { __sameDocument?: boolean }).__sameDocument = true
  })

  await page.getByLabel('New status').click()
  await page.getByRole('option', { name: 'Resolved' }).click()
  await page.getByLabel('Note (optional)').fill('Replaced the dock firmware.')
  await page.getByRole('button', { name: 'Update status' }).click()

  await expect(stepFor(page, 'Resolved')).toContainText('Replaced the dock firmware.')
  await expect(stepFor(page, 'Resolved')).not.toContainText('Not yet reached')
  // The request skipped straight from Open to Resolved, so those two are what
  // is left un-reached — an appended transition fills the step it names and
  // invents nothing about the ones it passed over.
  await expect(stepFor(page, 'In progress')).toContainText('Not yet reached')
  await expect(stepFor(page, 'Closed')).toContainText('Not yet reached')
  // Still four steps: the appended row merged into its status rather than
  // arriving as a fifth one.
  await expect(page.getByRole('listitem')).toHaveCount(4)

  expect(
    await page.evaluate(
      () => (window as unknown as { __sameDocument?: boolean }).__sameDocument,
    ),
  ).toBe(true)

  // Cleared for the next change rather than left holding the last one.
  await expect(page.getByLabel('Note (optional)')).toHaveValue('')

  // And it was really written, not merely shown: a fresh load finds it too.
  await page.reload()
  await expect(stepFor(page, 'Resolved')).toContainText('Replaced the dock firmware.')
})
