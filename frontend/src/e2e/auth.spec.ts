import {
  TEST_PASSWORD,
  expect,
  signIn,
  signedInAs,
  test,
  uniqueEmail,
  type TestUser,
} from './fixtures'

/**
 * The Auth slice's behaviour, as a person experiences it (T-DEBT-3).
 *
 * These assert what the user gets, not which functions ran — with one
 * deliberate exception in refresh-concurrency.spec.ts, where the guarantee
 * *is* a network pattern.
 */

test('registering, signing in and reloading keeps the session', async ({ page }) => {
  const user: TestUser = {
    email: uniqueEmail(),
    password: TEST_PASSWORD,
    first_name: 'Playwright',
    last_name: 'Journey',
  }

  await page.goto('/register')
  await page.getByLabel('First name').fill(user.first_name)
  await page.getByLabel('Last name').fill(user.last_name)
  await page.getByLabel('Email').fill(user.email)
  await page.getByLabel('Password', { exact: true }).fill(user.password)
  await page.getByLabel('Confirm password').fill(user.password)
  await page.getByRole('button', { name: 'Create account' }).click()

  // Registering does not sign anyone in — no cookies are set (design.md §2),
  // so the flow hands off to the login form with a real row now behind it.
  await expect(page.getByText('Account created')).toBeVisible()
  await expect(page).toHaveURL('/login')

  await signIn(page, user)

  // The point of the test. A reload throws away every scrap of in-memory
  // state, so a session that survives it can only have come back from
  // `GET /auth/me` reading a cookie this page is not allowed to see.
  await page.reload()
  await expect(page).toHaveURL('/')
  await expect(page.getByText(signedInAs(user))).toBeVisible()
})

test('a wrong password and an unknown email fail identically', async ({
  page,
  freshUser,
}) => {
  const attemptSignIn = async (email: string, password: string) => {
    await page.goto('/login')
    await page.getByLabel('Email').fill(email)
    await page.getByLabel('Password').fill(password)

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/auth/login')),
      page.getByRole('button', { name: 'Sign in' }).click(),
    ])

    // Both fields are filled and well-formed, so no field-level alert exists —
    // the only alert on the page is the failure banner.
    const banner = page.getByRole('alert')
    await expect(banner).toBeVisible()

    const body = (await response.json()) as { error: { message: string } }
    return {
      status: response.status(),
      banner: (await banner.textContent())?.trim(),
      serverMessage: body.error.message,
    }
  }

  const wrongPassword = await attemptSignIn(freshUser.email, 'not-the-right-password')
  const unknownEmail = await attemptSignIn(uniqueEmail(), TEST_PASSWORD)

  expect(wrongPassword.status).toBe(401)
  expect(unknownEmail.status).toBe(401)

  // AUTH-7: the two failures must be indistinguishable to the person at the
  // keyboard. The backend returns byte-identical bodies; this is the half of
  // that guarantee a UI can quietly undo by being helpful.
  expect(wrongPassword.banner).not.toBe('')
  expect(wrongPassword.banner).toBe(unknownEmail.banner)

  // And what's shown is the server's message rather than a local constant
  // that happens to match today — the distinction frontend/CLAUDE.md's Error
  // surfacing section draws, and the reason the hardcoded string was removed.
  expect(wrongPassword.banner).toBe(wrongPassword.serverMessage)
  expect(unknownEmail.banner).toBe(unknownEmail.serverMessage)
})

test('signing out ends the session on the server, not just in the tab', async ({
  page,
  freshUser,
}) => {
  await signIn(page, freshUser)

  await page.getByRole('button', { name: 'Sign out' }).click()
  await expect(page).toHaveURL('/login')

  // A cleared React state would pass a reload test by accident. This asserts
  // the server's own answer: the refresh token is revoked and the cookies are
  // gone (AUTH-12), so the bootstrap call comes back 401 and the guard sends
  // the visitor to /login.
  const [meResponse] = await Promise.all([
    page.waitForResponse((r) => r.url().includes('/auth/me')),
    page.goto('/'),
  ])

  expect(meResponse.status()).toBe(401)
  await expect(page).toHaveURL('/login')
  await expect(page.getByText(signedInAs(freshUser))).toHaveCount(0)
})

test('a signed-out visitor asking for a protected route lands on /login', async ({
  page,
}) => {
  await page.goto('/requests/new')

  await expect(page).toHaveURL('/login')
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
})
