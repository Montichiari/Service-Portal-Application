# `backend/evals/` — the tests that cost money

Everything in this directory calls the real Messages API with the real
`ANTHROPIC_API_KEY`. **Every run is billed**, and the model's answers are not
deterministic, so nothing here belongs in the suite that runs on every change.

## Why it is a separate directory and not a marker

`pytest.ini` sets `testpaths = tests`, so `python -m pytest` from `backend/`
never collects this directory at all — not as passes, not as skips, not as
"deselected by a marker". A marker would have left these tests one forgotten
`-m` flag away from running in CI, and the failure mode of that mistake is a
bill rather than a red build.

The other half of the guarantee lives in `tests/conftest.py`: an autouse
fixture unsets `ANTHROPIC_API_KEY` for every test in `tests/`, so even a test
that reaches `POST /chat/messages` without stubbing the client cannot place a
live call. Nothing under `tests/` can spend money; nothing here can avoid it.

> If you ever share fixtures the other way, import them by name. A
> `from tests.conftest import *` here would drag that autouse fixture in and
> silently unset the key for these tests too — they would fail claiming no key
> was configured while `.env` plainly has one.

## Running it

From `backend/`, with a working key in `.env`:

```bash
# everything (a handful of API calls)
python -m pytest evals -q -s

# just the live exchange — T-CHAT-1's first three acceptance criteria
python -m pytest evals/test_live_exchange.py -q -s

# just the tool-choice eval set (design.md §11)
python -m pytest evals/test_tool_choice.py -q -s
```

`-s` is worth having: the live exchange prints the full stored transcript —
every content block in order, as `GET /chat/messages` would return it — which
is the artefact worth reading when something looks wrong.

Without a key, every test here skips with a message saying so. That is the one
case where a skip is the honest answer: the tests did not pass, and they did
not fail either.

## What each file is for

| File                    | Subject                                                                                                                                                        |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_live_exchange.py` | The whole loop against a live model and a real database: a tool call that files a real request, an FAQ answer that files nothing, and CHAT-3's write-before-call |
| `test_tool_choice.py`   | design.md §11's eval set — fixed messages, each with an expected *tool choice*. Never an expected reply                                                          |

## The rule these tests follow

design.md §11: **never assert on model phrasing.** A reply is a sample from a
distribution, and a test that pins its wording fails the next time the model
improves. What is asserted here is what the model *did* — which tool it chose,
what reached the database — and what the code around it did with that.

Everything deterministic is already covered under `tests/`, against a stubbed
client, and that is where a regression should be caught first. These tests
exist for the one thing a stub cannot tell you: whether the system prompt and
the tool descriptions actually steer a real model to the right call.
