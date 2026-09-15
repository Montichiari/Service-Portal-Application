import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { useAuth } from '@/context/AuthContext'
import {
  MAX_PAGE_SIZE,
  getChatMessages,
  isApiError,
  sendChatMessage,
  type ChatMessage,
} from '@/lib/api'
import { useAsyncData, type Async } from '@/lib/async'
import { pageErrorMessage } from '@/lib/formErrors'
import { chatMessageSchema } from '@/schemas/chatMessageSchema'

/**
 * All of the chat widget's state (T-CHAT-2; specs/chatbot/design.md §9).
 *
 * **Everything the widget can show lives here, including the half-typed
 * message** — and that is a correctness requirement rather than tidiness.
 * CHAT-15 asks that the widget survive route navigation, and design.md §9's
 * answer is to mount it once inside `AppShell`. But `AppShell` in this app is
 * rendered *by each page*, not by a persistent layout route, so navigating
 * from `/` to `/requests/new` unmounts the whole shell subtree and mounts a
 * fresh one — the same reason `AppShell`'s own `menuOpen` resets on every nav.
 * A widget holding its own state would therefore lose the conversation exactly
 * when CHAT-15 says it must not. This provider sits above the router, so the
 * widget below it is a pure view and the remount is invisible.
 *
 * That is also why the draft is here and why this composer is the one form in
 * the app not built on `react-hook-form` (frontend/CLAUDE.md, Form pattern).
 * react-hook-form's whole value is owning form state; owning it in the
 * remounting half of the tree is the one thing this field cannot afford, since
 * CHAT-17's "without losing the user's typed message" would then hold for a
 * failed request but not for a navigation. The parts of the convention that
 * are about validation and error surfacing are kept intact: the rule is still
 * a zod schema in `schemas/`, a client-side failure and a server `422`'s
 * `fields.message` still land on the same inline slot through `Field`, and
 * anything not attributable to the field still goes to `ErrorBanner`.
 *
 * Context, provider and hook are colocated for the same reason `AuthContext`
 * colocates its own — they are one public surface — with the same
 * fast-refresh lint suppression on the hook.
 */

/**
 * One line of the transcript: the *text* of a stored message, not the message.
 *
 * The conversation on the wire carries blocks the user should never read —
 * `tool_use`, `tool_result`, and the signed `thinking` blocks Sonnet 5 returns
 * on some turns. Flattening to text here rather than in a component means the
 * widget never branches on a block type, and matches what `POST /chat/messages`
 * already does on the write path: it returns the final text and keeps the
 * machinery to itself (design.md §3 step 8).
 */
export interface ChatTurn {
  id: string
  role: 'user' | 'assistant'
  text: string
}

/** Stable identity, so a re-render can't hand `useMemo` a fresh empty array. */
const NO_TURNS: ChatTurn[] = []

/**
 * The text blocks of one stored message, joined, or `''` if it has none.
 *
 * A message with no text is not an empty turn to render — it is a `tool_use`
 * or a `tool_result`, i.e. a step of the loop rather than something anyone
 * said. Those are dropped entirely below.
 */
function turnText(message: ChatMessage): string {
  return message.content
    .flatMap((block) =>
      block.type === 'text' && typeof block.text === 'string' ? [block.text] : [],
    )
    .join('\n\n')
    .trim()
}

function toTurns(messages: ChatMessage[]): ChatTurn[] {
  const turns: ChatTurn[] = []
  for (const message of messages) {
    const text = turnText(message)
    if (text === '') continue
    // Keyed by the message's real id — one message becomes at most one turn,
    // so the id stays unique across the list.
    turns.push({ id: message.id, role: message.role, text })
  }
  return turns
}

// Turns added locally after a successful send have no server id until the next
// load. A module-level counter rather than `crypto.randomUUID()`: these are
// React keys, they only have to be unique within one page's lifetime, and a
// counter makes that obvious at a glance.
let localTurnSequence = 0

function localTurn(role: ChatTurn['role'], text: string): ChatTurn {
  localTurnSequence += 1
  return { id: `local-${localTurnSequence}`, role, text }
}

/**
 * The recent end of the caller's conversation.
 *
 * Two requests rather than one, and only for a conversation long enough to
 * need it. `GET /chat/messages` is oldest-first and paginated (XC-10), so the
 * first page of a 150-message conversation is the *oldest* 100 — showing those
 * and then appending new replies underneath would leave an unsignalled hole in
 * the middle, which is worse than the round trip. The widget has no "load
 * earlier" control, so the last page is the honest thing to show.
 *
 * The second call reuses `page_size` from the first response, not the constant
 * that was asked for: XC-11 clamps rather than rejects, so the server's own
 * value is the only one guaranteed to line the two pages up.
 */
async function loadRecentTurns(signal: AbortSignal): Promise<ChatTurn[]> {
  const first = await getChatMessages({ page: 1, page_size: MAX_PAGE_SIZE }, signal)
  if (first.total <= first.items.length) return toTurns(first.items)

  const lastPage = Math.ceil(first.total / first.page_size)
  const last = await getChatMessages(
    { page: lastPage, page_size: first.page_size },
    signal,
  )
  return toTurns(last.items)
}

interface ChatContextValue {
  /** Whether the panel is showing. Survives navigation; see the file header. */
  isOpen: boolean
  /** Opens the panel *and* (re)loads the conversation — see `openCount` below. */
  open: () => void
  close: () => void
  /** Reloads the conversation without touching `isOpen`, for the error state. */
  retry: () => void
  /** The transcript: loaded history plus everything sent since it loaded. */
  transcript: Async<ChatTurn[]>
  /** The composer's contents. Cleared only by a reply actually arriving. */
  draft: string
  setDraft: (value: string) => void
  /** Validates, posts, and appends both turns on success. Never throws. */
  send: () => Promise<void>
  /** CHAT-16 — true for the whole round trip, which is a slow one. */
  isSending: boolean
  /** A `422` on the message itself: shown inline under the field. */
  draftError: string | null
  /** CHAT-17 — anything else, shown as a banner above a still-filled input. */
  sendError: string | null
}

const ChatContext = createContext<ChatContextValue | null>(null)

export function ChatProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const userId = user?.id ?? null

  const [isOpen, setIsOpen] = useState(false)
  // Bumped on every open, and part of the load's dependency list, so the
  // conversation is fetched the first time the widget is opened (never before
  // — a user who ignores the assistant pays no request for it) and refetched
  // on each reopen. That refetch is also the recovery path from a failed load:
  // closing and reopening genuinely retries rather than re-showing a stale
  // error, and `retry` below is the same move without the close.
  const [openCount, setOpenCount] = useState(0)
  const [draft, setDraftValue] = useState('')
  const [draftError, setDraftError] = useState<string | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)
  const [isSending, setIsSending] = useState(false)

  const history = useAsyncData<ChatTurn[]>(
    (signal) =>
      openCount > 0 && userId !== null
        ? loadRecentTurns(signal)
        : // Not "no messages" — "not asked yet". It never reaches the screen:
          // the panel is closed, and opening it changes `openCount`, which
          // puts this straight back to pending before anything renders.
          Promise.resolve(NO_TURNS),
    [openCount, userId],
  )

  /*
   * Turns sent since this load, held separately and concatenated at read time
   * — the same shape `RequestComments` uses for posted comments, for the same
   * reason: refetching after a write returns the transcript to `pending`, and
   * the user would watch the message they just sent take the conversation away
   * with it.
   *
   * Keyed by user *and* load, because both make these redundant. A reload
   * fetches them back from the server (they were persisted by CHAT-10), and a
   * different user must never inherit them at all.
   */
  const loadKey = `${userId ?? ''}:${openCount}`
  const [sent, setSent] = useState<{ key: string; turns: ChatTurn[] }>({
    key: loadKey,
    turns: NO_TURNS,
  })
  const appended = sent.key === loadKey ? sent.turns : NO_TURNS

  /*
   * Signing out must not leave the next user looking at the previous one's
   * conversation or half-typed message. The transcript itself is covered by
   * `userId` being in both keys above; this resets what is keyed on nothing.
   *
   * Done during render against a remembered previous value — React's own
   * adjust-state-when-a-prop-changes pattern — rather than in an effect. An
   * effect would paint the stale panel once before clearing it, which for a
   * sign-out means one frame of the previous user's draft on screen.
   */
  const [lastUserId, setLastUserId] = useState(userId)
  if (lastUserId !== userId) {
    setLastUserId(userId)
    setIsOpen(false)
    setOpenCount(0)
    setDraftValue('')
    setDraftError(null)
    setSendError(null)
  }

  const transcript = useMemo<Async<ChatTurn[]>>(
    () =>
      history.status === 'ready'
        ? { status: 'ready', data: [...history.data, ...appended] }
        : history,
    [history, appended],
  )

  const open = useCallback(() => {
    setIsOpen(true)
    setOpenCount((count) => count + 1)
  }, [])

  const close = useCallback(() => setIsOpen(false), [])

  const retry = useCallback(() => setOpenCount((count) => count + 1), [])

  const setDraft = useCallback((value: string) => {
    setDraftValue(value)
    // Both errors are answers to a send that already happened; editing the
    // message makes them stale. Same clearing rule the comment composer uses.
    setDraftError(null)
    setSendError(null)
  }, [])

  const send = useCallback(async () => {
    const parsed = chatMessageSchema.safeParse({ message: draft })
    if (!parsed.success) {
      setDraftError(parsed.error.issues[0].message)
      return
    }

    const { message } = parsed.data
    setDraftError(null)
    setSendError(null)
    setIsSending(true)

    try {
      const { reply } = await sendChatMessage({ message })
      // The reply is the server's; the user's line is the exact string that
      // was sent, so nothing here is invented — and `GET /chat/messages` on
      // the next open replaces both with what was actually persisted.
      const turns = [localTurn('user', message), localTurn('assistant', reply)]
      setSent((previous) =>
        previous.key === loadKey
          ? { key: loadKey, turns: [...previous.turns, ...turns] }
          : { key: loadKey, turns },
      )
      // CHAT-17, the other way round: the draft is cleared **here**, once a
      // reply has actually come back, and nowhere else. Clearing it on submit
      // would be optimistic about a multi-second call that can fail, and the
      // failure branch below would have nothing left to hand back.
      setDraftValue('')
    } catch (error) {
      // `applyFieldErrors` is react-hook-form's shape (it takes a
      // `UseFormSetError`), so the one field this composer has reads its own
      // entry out of XC-4's map directly. Same destination, same rendering.
      const messages = isApiError(error) ? error.fields?.message : undefined
      if (messages !== undefined && messages.length > 0) {
        setDraftError(messages.join(' '))
      } else {
        setSendError(pageErrorMessage(error))
      }
      // `draft` is deliberately untouched on every branch out of here.
    } finally {
      setIsSending(false)
    }
  }, [draft, loadKey])

  const value = useMemo<ChatContextValue>(
    () => ({
      isOpen,
      open,
      close,
      retry,
      transcript,
      draft,
      setDraft,
      send,
      isSending,
      draftError,
      sendError,
    }),
    [
      isOpen,
      open,
      close,
      retry,
      transcript,
      draft,
      setDraft,
      send,
      isSending,
      draftError,
      sendError,
    ],
  )

  return <ChatContext.Provider value={value}>{children}</ChatContext.Provider>
}

// oxlint-disable-next-line react/only-export-components -- hook belongs with its context; see file header
export function useChat(): ChatContextValue {
  const context = useContext(ChatContext)
  if (context === null) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return context
}
