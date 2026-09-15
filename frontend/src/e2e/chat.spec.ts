import { expect, signIn, test } from './fixtures'
import type { Page, Route } from '@playwright/test'

/**
 * The chat widget (T-CHAT-2; CHAT-15, CHAT-16, CHAT-17).
 *
 * **`POST /chat/messages` is stubbed here; `GET /chat/messages` is not.** That
 * is a deliberate exception to this suite's run-against-the-real-stack rule,
 * and the design already draws the line in the same place: §11 splits chat
 * testing into deterministic tests and model-in-the-loop evals precisely
 * because a live exchange is metered, slow, and free to phrase its reply
 * however it likes. Two of the three criteria below are *about* the network —
 * a reply that has not arrived yet (CHAT-16) and one that never will
 * (CHAT-17) — which is the same exception the refresh-concurrency spec takes:
 * where the behaviour under test is a network pattern, the network is what the
 * test has to drive. The read path stays real, as does the session, the
 * cookies and every route the widget renders inside.
 *
 * The stub also makes the persistence test sharper than a live call would. A
 * stubbed reply is never written to `chat_messages`, so it exists nowhere but
 * in the provider's memory — a widget that survived navigation by refetching
 * its history rather than by outliving the remount would come back empty.
 */

const CHAT_ENDPOINT = '**/api/v1/chat/messages'

/** Long enough to observe the pending state, short enough not to pad the run. */
const HOLD_RESPONSE_MS = 1500

/**
 * Stand in for the assistant on the write path only.
 *
 * `GET` is explicitly handed back to the network: the widget loads its history
 * from the real backend on every open, and intercepting that would mean the
 * transcript never crosses the wire at all.
 */
async function stubAssistant(
  page: Page,
  reply: string,
  options: { delayMs?: number } = {},
): Promise<void> {
  await page.route(CHAT_ENDPOINT, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    if (options.delayMs !== undefined) {
      await new Promise((resolve) => setTimeout(resolve, options.delayMs))
    }
    await fulfilReply(route, reply)
  })
}

function fulfilReply(route: Route, reply: string): Promise<void> {
  return route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ reply }),
  })
}

function panelOf(page: Page) {
  return page.getByRole('dialog', { name: 'IT assistant' })
}

async function openWidget(page: Page) {
  await page.getByRole('button', { name: 'Assistant' }).click()
  const panel = panelOf(page)
  // The conversation loads on open, so waiting for the composer to be usable
  // is waiting for a real `GET /chat/messages` to have come back.
  await expect(panel.getByLabel('Message')).toBeEnabled()
  return panel
}

test('the widget and its conversation survive a route change', async ({
  page,
  freshUser,
}) => {
  const reply = 'Use the “Forgot password” link on the sign-in page.'
  await signIn(page, freshUser)
  await stubAssistant(page, reply)

  const panel = await openWidget(page)
  await panel.getByLabel('Message').fill('How do I reset my password?')
  await panel.getByRole('button', { name: 'Send' }).click()
  await expect(panel.getByText(reply)).toBeVisible()

  // A sentinel only a document navigation can clear (the T-CM-1 technique).
  // Without it this would pass on a full page load too — which is the one
  // outcome CHAT-15 rules out, and the one a visibility assertion cannot see.
  await page.evaluate(() => {
    ;(window as unknown as Record<string, string>).chatNavigationSentinel = 'set'
  })

  await page.getByRole('link', { name: 'Submit Request' }).click()
  await expect(page).toHaveURL('/requests/new')

  expect(
    await page.evaluate(
      () => (window as unknown as Record<string, string>).chatNavigationSentinel,
    ),
    'the route change was a full page load, not a client-side navigation',
  ).toBe('set')

  // Still open, and still holding a reply that was never persisted anywhere —
  // so this is the same widget state, not a fresh one that reloaded itself.
  await expect(panel).toBeVisible()
  await expect(panel.getByText(reply)).toBeVisible()
})

test('a message in flight shows a pending state (CHAT-16)', async ({
  page,
  freshUser,
}) => {
  const reply = 'Restart the VPN client and check your connection.'
  await signIn(page, freshUser)
  await stubAssistant(page, reply, { delayMs: HOLD_RESPONSE_MS })

  const panel = await openWidget(page)
  await panel.getByLabel('Message').fill('My VPN will not connect.')
  await panel.getByRole('button', { name: 'Send' }).click()

  // The whole point of the requirement: a multi-second tool loop must not look
  // like a frozen widget.
  await expect(panel.getByText('Assistant is typing…')).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Sending…' })).toBeDisabled()

  await expect(panel.getByText(reply)).toBeVisible()
  await expect(panel.getByText('Assistant is typing…')).toBeHidden()
  await expect(panel.getByRole('button', { name: 'Send' })).toBeEnabled()
})

test('a failed send keeps the typed message and can be retried (CHAT-17)', async ({
  page,
  freshUser,
}) => {
  const message = 'My printer is offline in the west meeting room.'
  const reply = 'I have logged a request for the printer.'
  await signIn(page, freshUser)

  // Both failures CHAT-17 names, then the success. Read at handler entry and
  // never across an await — the T-DEBT-3 finding was a route handler reading a
  // shared value back *after* awaiting, so the branch it selected was not the
  // branch it appeared to select.
  let outcome: 'network' | 'server-error' | 'reply' = 'network'
  await page.route(CHAT_ENDPOINT, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    switch (outcome) {
      case 'network':
        return route.abort('failed')
      case 'server-error':
        return route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            error: { code: 'INTERNAL_ERROR', message: 'Internal server error.' },
          }),
        })
      case 'reply':
        return fulfilReply(route, reply)
    }
  })

  const panel = await openWidget(page)
  const input = panel.getByLabel('Message')
  await input.fill(message)

  await panel.getByRole('button', { name: 'Send' }).click()
  await expect(panel.getByRole('alert')).toBeVisible()
  // The requirement, exactly: the request failed and the message is still
  // there to send again. Nothing to retype, no draft to reconstruct.
  await expect(input).toHaveValue(message)

  outcome = 'server-error'
  await panel.getByRole('button', { name: 'Send' }).click()
  await expect(panel.getByRole('alert')).toContainText('Internal server error.')
  await expect(input).toHaveValue(message)

  // Retryable means the same click works once the failure clears.
  outcome = 'reply'
  await panel.getByRole('button', { name: 'Send' }).click()
  await expect(panel.getByText(reply)).toBeVisible()
  await expect(panel.getByText(message)).toBeVisible()
  // Cleared only now — a reply actually came back. This is the other half of
  // the assertion above: holding the draft through a failure is worth nothing
  // if it is also held through a success.
  await expect(input).toHaveValue('')
  await expect(panel.getByRole('alert')).toBeHidden()
})

const MOBILE_WIDTH = 375

test('the panel fits a 375px viewport', async ({ page, freshUser }) => {
  await signIn(page, freshUser)
  await stubAssistant(page, 'Reply.')
  await page.setViewportSize({ width: MOBILE_WIDTH, height: 720 })

  // Below --bp-mobile the sidebar is a top bar with a menu toggle, so the
  // launcher has to be reachable without it.
  const panel = await openWidget(page)
  await expect(panel.getByRole('button', { name: 'Send' })).toBeVisible()

  /*
   * Measured, not inferred from the document's width. The first version of
   * this asserted `scrollWidth <= clientWidth` and passed with the desktop
   * panel forced on at every width — a `position: fixed` box never widens the
   * document, so the check could not fail for the reason it named. Another
   * entry in the running tally: the test was green and the thing it claimed
   * was false.
   */
  const box = await panel.boundingBox()
  if (box === null) throw new Error('the panel is open but has no layout box')
  expect(box.x, 'the panel starts off the left edge of the screen').toBeGreaterThanOrEqual(0)
  expect(
    box.x + box.width,
    'the panel runs off the right edge of the screen',
  ).toBeLessThanOrEqual(MOBILE_WIDTH)
})

test('the assistant is not offered to a signed-out visitor', async ({ page }) => {
  // The not-found page is framed by AppShell and is public on purpose, which
  // is the one way this widget can render without a session — and CHAT-13
  // gives chat no auth path of its own, so it would only produce a 401.
  await page.goto('/no-such-page')
  await expect(page.getByRole('heading', { name: 'Page not found' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Assistant' })).toHaveCount(0)
})
