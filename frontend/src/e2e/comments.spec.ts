import {
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
 * The Comments slice's behaviour (T-CM-1), against the real stack.
 *
 * Two of these are about what an admin sees, which is why `promoteToAdmin`
 * exists: T-DEBT-5 verified the requestor column by promoting an account by
 * hand, and a check that only ever happened by hand is one nothing is holding
 * on to (task-log.md#t-debt-5).
 *
 * Every test here was verified by removing the thing it names and watching it
 * go red, per backend/CLAUDE.md's rule applied to the frontend — a test never
 * observed to fail is not verified, only written.
 */

/** A body no other row in the database will share, so a locator can't collide. */
function uniqueBody(prefix: string): string {
  return `${prefix} ${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

test('a regular user gets no internal-comment checkbox at all', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)
  const owned = await createRequestViaApi(request, {
    title: uniqueTitle('Printer jammed'),
    description: 'Third floor printer reports a paper jam that is not there.',
    priority: 'low',
  })

  await signIn(page, freshUser)
  await page.goto(`/requests/${owned.id}`)

  // The composer itself is for everyone — CM-5 lets any caller who can see the
  // request comment on it.
  await expect(page.getByLabel('Add a comment')).toBeVisible()

  // The checkbox is not in the DOM, rather than hidden or disabled. CM-7 is
  // enforced server-side with a 403 regardless, so this is about not offering
  // a control whose only outcome would be a rejection.
  await expect(page.getByLabel('Internal note')).toHaveCount(0)
})

test('posting a comment appends it to the thread without a page reload', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)
  const owned = await createRequestViaApi(request, {
    title: uniqueTitle('Laptop battery swelling'),
    description: 'The case has started to separate around the trackpad.',
    priority: 'high',
  })

  await signIn(page, freshUser)
  await page.goto(`/requests/${owned.id}`)

  // A request nobody has commented on is `ready` with an empty array, not an
  // error and not a fourth union state.
  await expect(page.getByText('No comments yet.')).toBeVisible()

  // Survives anything short of a document navigation, so it is what tells an
  // in-place append from a reload that happens to end up looking the same.
  await page.evaluate(() => {
    ;(window as unknown as { __sameDocument?: boolean }).__sameDocument = true
  })

  const body = uniqueBody('Booking a swap with the service desk.')
  await page.getByLabel('Add a comment').fill(body)
  await page.getByRole('button', { name: 'Post comment' }).click()

  await expect(page.getByText(body)).toBeVisible()
  await expect(page.getByText('No comments yet.')).toHaveCount(0)
  // Cleared for the next comment rather than left holding the last one.
  await expect(page.getByLabel('Add a comment')).toHaveValue('')

  expect(
    await page.evaluate(
      () => (window as unknown as { __sameDocument?: boolean }).__sameDocument,
    ),
  ).toBe(true)

  // And it was really written, not merely shown: a fresh load finds it too.
  await page.reload()
  await expect(page.getByText(body)).toBeVisible()
})

test("the admin dashboard names each request's own requestor", async ({
  page,
  request,
  browser,
}) => {
  // T-DEBT-5 debt: the requestor column was checked by hand and never captured.
  // The failure it guards against — rendering the *viewer's* name on every row
  // — is invisible unless two rows have two different requestors, which is why
  // this seeds two named users rather than reusing the shared default.
  const ada = await registerViaApi(request, {
    first_name: 'Ada',
    last_name: 'Lovelace',
  })
  const grace = await registerViaApi(request, {
    first_name: 'Grace',
    last_name: 'Hopper',
  })
  const admin = await registerViaApi(request, {
    first_name: 'Sam',
    last_name: 'Supervisor',
  })
  promoteToAdmin(admin)

  // Each request is filed by its own user, on its own cookie jar — a second
  // context, so signing one in does not sign the other out.
  await signInViaApi(request, ada)
  const adasRequest = await createRequestViaApi(request, {
    title: uniqueTitle('Analytical engine access'),
    description: 'Needs an account on the shared compute cluster.',
    priority: 'medium',
  })

  const graceContext = await browser.newContext()
  await signInViaApi(graceContext.request, grace)
  const gracesRequest = await createRequestViaApi(graceContext.request, {
    title: uniqueTitle('Compiler licence renewal'),
    description: 'The team licence lapses at the end of the month.',
    priority: 'medium',
  })
  await graceContext.close()

  await signIn(page, admin)

  // SR-2 puts both on the admin's dashboard, newest first (SR-15), so both are
  // on page one.
  const rowFor = (title: string) => page.getByRole('row').filter({ hasText: title })

  await expect(rowFor(adasRequest.title)).toContainText('Ada Lovelace')
  await expect(rowFor(gracesRequest.title)).toContainText('Grace Hopper')
  // The specific bug: the viewer's own name repeated down the column.
  await expect(rowFor(adasRequest.title)).not.toContainText('Sam Supervisor')
  await expect(rowFor(gracesRequest.title)).not.toContainText('Sam Supervisor')
})

test('an internal comment reaches the admin only, badged as internal', async ({
  page,
  request,
  freshUser,
}) => {
  await signInViaApi(request, freshUser)
  const owned = await createRequestViaApi(request, {
    title: uniqueTitle('VPN drops every ten minutes'),
    description: 'Reconnects on its own but loses the session each time.',
    priority: 'high',
  })

  const admin = await registerViaApi(request, {
    first_name: 'Sam',
    last_name: 'Supervisor',
  })
  promoteToAdmin(admin)

  await signIn(page, admin)
  await page.goto(`/requests/${owned.id}`)

  const publicBody = uniqueBody('Raising this with the network team.')
  const internalBody = uniqueBody('Suspect the concentrator, not the client.')

  await page.getByLabel('Add a comment').fill(publicBody)
  await page.getByRole('button', { name: 'Post comment' }).click()
  await expect(page.getByText(publicBody)).toBeVisible()

  await page.getByLabel('Add a comment').fill(internalBody)
  await page.getByLabel('Internal note').check()
  await page.getByRole('button', { name: 'Post comment' }).click()

  // The badge is what tells an admin which of the comments in front of them
  // the requestor cannot read — without it, writing one is guesswork.
  const internalRow = page.getByRole('listitem').filter({ hasText: internalBody })
  await expect(internalRow).toContainText('Internal')
  await expect(
    page.getByRole('listitem').filter({ hasText: publicBody }),
  ).not.toContainText('Internal')

  // CM-2 filters internal comments out of a regular user's response at the
  // query level, so the requestor never receives the row — this is a check on
  // the whole stack, not on what the UI chose to render.
  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL('/login')

  await signIn(page, freshUser)
  await page.goto(`/requests/${owned.id}`)

  await expect(page.getByText(publicBody)).toBeVisible()
  await expect(page.getByText(internalBody)).toHaveCount(0)
  await expect(page.getByText('Internal', { exact: true })).toHaveCount(0)
})
