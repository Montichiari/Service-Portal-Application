import { useEffect, useRef } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { MessageSquareIcon, XIcon } from 'lucide-react'
import { AsyncSection } from '@/components/ui/AsyncSection'
import { Button } from '@/components/ui/Button'
import { ErrorBanner } from '@/components/ui/ErrorBanner'
import { Field } from '@/components/ui/Field'
import { Textarea } from '@/components/ui/Textarea'
import { useAuth } from '@/context/AuthContext'
import { useChat, type ChatTurn } from '@/context/ChatContext'
import { cn } from '@/lib/utils'
import { MAX_CHAT_MESSAGE_CHARS } from '@/schemas/chatMessageSchema'

/**
 * The AI assistant widget (T-CHAT-2; specs/chatbot/design.md §9) — a launcher
 * and the panel it opens, mounted once by `AppShell` rather than per page.
 *
 * This component holds **no state of its own**. Every piece of it —
 * open/closed, the transcript, the draft, the pending flag, both error slots —
 * comes from `ChatContext`, which sits above the router. That is what makes
 * CHAT-15 true in this app rather than merely intended: `AppShell` is rendered
 * by each page, so this subtree is torn down and rebuilt on every navigation,
 * and anything it owned would go with it. The remount is invisible because
 * there is nothing here to lose.
 *
 * Responsive per design-tokens.md "Breakpoints" (`--bp-mobile`, Tailwind's
 * `md`): below the breakpoint the panel fills the viewport inside a gutter,
 * which is the only honest use of a 375px screen for a conversation; at and
 * above it, a fixed panel in the bottom-right corner
 * (`--chat-panel-width`/`--chat-panel-height`).
 *
 * Not a modal: the page behind stays usable and focus is not trapped, so there
 * is no `aria-modal` and no scroll lock. The assistant is a side channel to
 * whatever the user is already doing — taking the page hostage while it thinks
 * would be the opposite of the point.
 */
export function ChatWidget() {
  const { user } = useAuth()
  const {
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
  } = useChat()

  const scrollRef = useRef<HTMLDivElement>(null)

  // Keep the newest turn in view, including the typing line — a reply that
  // lands below the fold reads as nothing having happened.
  const turnCount = transcript.status === 'ready' ? transcript.data.length : 0
  useEffect(() => {
    const node = scrollRef.current
    if (node !== null) node.scrollTop = node.scrollHeight
  }, [turnCount, isSending, isOpen])

  // `AppShell` also frames the not-found page, which is public on purpose, so
  // a signed-out visitor can reach this component. CHAT-13 puts both chat
  // routes behind the same session as everything else, so offering the
  // assistant there would only produce a `401` the moment it was used.
  if (user === null) return null

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={open}
        aria-haspopup="dialog"
        className="fixed right-4 bottom-4 z-40 inline-flex items-center gap-2 rounded-card bg-accent px-4 py-3 text-body font-semibold text-on-fill transition-opacity hover:opacity-90 focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 focus-visible:outline-none md:right-6 md:bottom-6"
      >
        <MessageSquareIcon className="size-4" />
        Assistant
      </button>
    )
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void send()
  }

  // Enter sends, Shift+Enter breaks the line — the convention for a chat
  // composer, and the reason this is a textarea rather than a text input: a
  // pasted error message keeps its shape.
  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey) return
    event.preventDefault()
    void send()
  }

  // The composer is mounted inside the ready branch below for the same reason
  // the comment composer is: a write box under an error banner accepts a
  // message with nowhere to show it. While the conversation is loading or
  // failed, the controls are present but inert, so the panel does not resize
  // under the user as it settles.
  const canSend = transcript.status === 'ready' && !isSending

  return (
    <section
      role="dialog"
      aria-label="IT assistant"
      className="fixed inset-x-4 top-4 bottom-4 z-40 flex flex-col overflow-hidden rounded-card border border-border bg-card md:inset-auto md:right-6 md:bottom-6 md:h-chat-panel-height md:w-chat-panel-width"
    >
      <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <h2 className="text-subhead font-semibold text-text-primary">
          IT assistant
        </h2>
        <button
          type="button"
          onClick={close}
          aria-label="Close the assistant"
          className="rounded-card p-1 text-text-secondary transition-colors hover:text-text-primary focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none"
        >
          <XIcon className="size-5" />
        </button>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3">
        <AsyncSection state={transcript} loadingLabel="Loading your conversation…">
          {(turns) => (
            <div className="flex flex-col gap-3">
              {/*
               * Empty is `ready` with an empty array, not a fourth state. A
               * user who has never messaged the assistant has no conversation
               * row at all (CHAT-1 creates it on first send), which is an
               * ordinary answer — so it gets an opening line naming what the
               * assistant can actually do, rather than a banner.
               */}
              {turns.length === 0 ? (
                <p className="text-dense text-text-secondary">
                  Ask an IT question, check a request you’ve submitted, or
                  describe a problem and I can file a request for you.
                </p>
              ) : (
                <ul className="flex list-none flex-col gap-3 p-0">
                  {turns.map((turn) => (
                    <ChatTurnItem key={turn.id} turn={turn} />
                  ))}
                </ul>
              )}

              {/*
               * CHAT-16. The call runs the whole tool loop synchronously
               * (design.md §9) — seconds, not milliseconds — so this is the
               * difference between "thinking" and "broken". `status`, not
               * `alert`: it is progress, not a problem.
               */}
              {isSending ? (
                <p role="status" className="text-dense text-text-secondary">
                  Assistant is typing…
                </p>
              ) : null}
            </div>
          )}
        </AsyncSection>

        {/*
         * AsyncSection has rendered the server's own message above; this adds
         * the way out. Closing and reopening the panel reloads too — this is
         * that same move without making the user guess it.
         */}
        {transcript.status === 'error' ? (
          <Button variant="secondary" className="mt-3" onClick={retry}>
            Try again
          </Button>
        ) : null}
      </div>

      <form
        className="flex flex-col gap-2 border-t border-border px-4 py-3"
        noValidate
        onSubmit={handleSubmit}
      >
        {/*
         * CHAT-17. A network failure or a 5xx lands here, above an input that
         * still holds what the user typed — so "retry" is one click of Send,
         * with nothing to retype.
         */}
        {sendError !== null ? <ErrorBanner message={sendError} /> : null}

        <Field label="Message" htmlFor="chat-message" error={draftError ?? undefined}>
          <Textarea
            id="chat-message"
            rows={2}
            className="min-h-0 resize-none"
            placeholder="Type your message…"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={!canSend}
            aria-invalid={draftError !== null ? true : undefined}
          />
        </Field>

        <div className="flex items-center justify-between gap-2">
          {/*
           * CHAT-14's ceiling, shown only once it is close enough to matter —
           * a counter sitting under every message would be noise for the two
           * lines most of them are. The server enforces the same number, so
           * this is a warning, not the rule.
           */}
          <span
            className={cn(
              'text-meta',
              draft.length > MAX_CHAT_MESSAGE_CHARS
                ? 'text-danger'
                : 'text-text-secondary',
            )}
          >
            {draft.length > MAX_CHAT_MESSAGE_CHARS / 2
              ? `${draft.length} / ${MAX_CHAT_MESSAGE_CHARS}`
              : ''}
          </span>
          {/* Disabled for the duration of the call, not merely after it
              succeeds: a second click would start a second metered exchange
              (CHAT-18 defers rate limiting to Phase 6), the same
              double-submit fix every other form here made. */}
          <Button type="submit" disabled={!canSend}>
            {isSending ? 'Sending…' : 'Send'}
          </Button>
        </div>
      </form>
    </section>
  )
}

/**
 * One line of the conversation.
 *
 * The visual side (right and filled, or left and outlined) is the only thing
 * saying who spoke, which a screen reader cannot see — hence the visually
 * hidden attribution. Without it the transcript reads as one undifferentiated
 * block of alternating sentences.
 */
function ChatTurnItem({ turn }: { turn: ChatTurn }) {
  const isUser = turn.role === 'user'
  return (
    <li className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[85%] rounded-card px-3 py-2 text-body whitespace-pre-line',
          isUser
            ? 'bg-accent text-on-fill'
            : 'border border-border bg-surface text-text-primary',
        )}
      >
        <span className="sr-only">{isUser ? 'You said: ' : 'Assistant said: '}</span>
        {turn.text}
      </div>
    </li>
  )
}
