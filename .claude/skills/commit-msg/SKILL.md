---
name: commit-msg
description: Use when asked to "write a commit message", "generate a commit", "commit my changes", or when /commit-msg is run. Generates a structured commit message from the staged diff and commits.
---

When generating a commit message:

1. Run `git diff --staged`. If it produces no output, stop and tell the user to
   stage their changes first — do not commit, do not `git add` anything yourself.
2. Read the full staged diff to understand what changed and why.
3. Compose a commit message in exactly this format:

   ```
   type(scope): short subject

   - bullet of what changed
   - bullet of why
   ```

   - `type` is one of: `feature`, `fix`, `refactor`, `chore`, `docs`, `style`, `test`
   - `scope` is a short area name derived from the diff (e.g. `entries`, `api`, `frontend`)
   - Subject line under 60 characters, no trailing period
   - The body bullets are compulsory — always at least one "what" bullet and one
     "why" bullet. Never omit the body.
4. Commit with `git commit -m "<message>"` (pass the multi-line message via a
   heredoc so the body is preserved). Only commit what is already staged.
5. After committing, show the user the final message and the resulting `git log -1 --stat`.
