import { z } from 'zod'

/**
 * Chat composer shape, reconciled against specs/chatbot/requirements.md
 * (CHAT-14) — the permanent source of truth for this constraint, the same way
 * specs/api-phase/requirements.md is for every other form here.
 *
 *   - message — non-empty, at most 4000 characters
 *
 * The ceiling is the API's own, measured the same way on both sides
 * (characters, not bytes), so nothing this composer accepts is refused by the
 * server and nothing it refuses would have been accepted. Unlike
 * `submitRequestSchema`'s description there is no UX cap sitting below a
 * larger backstop: decision 6 names one number and means it — the limit bounds
 * cost as much as misuse, since every character is replayed to the model on
 * every later call of the conversation.
 *
 * The limit is exported rather than only spelled into the message, because the
 * composer shows a live character count against it. Two independent copies of
 * one number is how the count and the rule would drift apart.
 */
export const MAX_CHAT_MESSAGE_CHARS = 4000

export const chatMessageSchema = z.object({
  message: z
    .string()
    .trim()
    .min(1, 'Enter a message')
    .max(
      MAX_CHAT_MESSAGE_CHARS,
      `Message must be ${MAX_CHAT_MESSAGE_CHARS} characters or fewer`,
    ),
})

export type ChatMessageValues = z.infer<typeof chatMessageSchema>
