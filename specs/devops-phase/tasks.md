# Phase 4 — DevOps & Cloud Deployment: Tasks

Ordered Claude Code prompts. One task per session, `/clear` between tasks, manual review and
commit before the next.

## T-DO-0 — Backend health-check endpoint

**Goal**: An unauthenticated endpoint the deployment pipeline and ALB can use to confirm the
service is live _and_ can reach the database.
**Covers**: DO-22
**Scope**: `GET /health`, no auth, does a trivial DB round-trip so a broken connection string
surfaces here rather than as an unexplained 500 later.
**Acceptance**:

- Returns 200 with no auth required.
- Returns a non-200 status if the database is unreachable (verify by temporarily pointing it at
  a broken connection string).
- Response body contains no connection string, stack trace, or other internal detail.

## T-DO-1 — Backend Dockerfile

**Goal**: A reproducible container image for the backend.
**Covers**: DO-1, DO-3, DO-4
**Scope**: Non-root user inside the image; all config via environment variables; no `.env` file
baked in.
**Acceptance**:

- Image builds successfully.
- Runs correctly against the existing local Postgres container.
- `/health` returns 200 when run this way.
- Image contains no secrets (inspect layers to confirm).

## T-DO-DEBT-1 — Pin backend dependencies

**Goal**: Close the reproducibility gap T-DO-1 surfaced — an unpinned `requirements.txt` let the
built image resolve different (newer) versions than the dev venv.
**Covers**: DO-23
**Scope**: Pin `requirements.txt` to the exact versions already resolved and tested inside
T-DO-1's image (freeze from that container, not the local dev venv) — the pinned set should be
the one already proven against all 376 tests and the full click-through, not a fresh re-resolve.
Update the local dev venv to match the same pins so dev and image stay in lockstep.
**Acceptance**:

- `requirements.txt` lists exact (`==`) versions for every installed package, direct and
  transitive.
- A fresh `pip install -r requirements.txt` into a clean venv produces the identical version set
  on a second, independent run.
- Full backend test suite still green against the pinned versions.
- Rebuilding T-DO-1's Docker image with the pinned `requirements.txt` still passes all four of
  T-DO-1's acceptance criteria.

## T-DO-2 — Frontend Dockerfile (build stage only)

**Goal**: A reproducible build of the frontend static assets.
**Covers**: DO-2, DO-23
**Scope**: Multi-stage Docker build producing `dist/`; no server runs inside the image — it's a
build tool, not a runtime. Use `npm ci`, not `npm install`, so the build resolves exactly what
`package-lock.json` pins rather than a range — same reproducibility reasoning as `DO-23`.
**Acceptance**: `docker build` output matches a local `npm run build` (functionally equivalent).

## T-DO-3 — Local prod-like stack validation

**Goal**: Confirm the built images actually work together before anything touches AWS.
**Covers**: Verification of DO-1 – DO-4
**Scope**: A compose file running the _built_ images (not source, not dev servers) together.
**Acceptance**: Full click-through — log in, submit a request, see it on the dashboard — using
only built artifacts, no source-mounted volumes.

## T-DO-4 (Manual, AWS Console) — Provision core infrastructure

**Goal**: Stand up the AWS resources this phase depends on.
**Covers**: DO-5 – DO-9, DO-16
**Scope**: VPC/subnets/security group, ECR repository, ECS cluster + service + task definition,
ALB, RDS instance, S3 bucket, CloudFront distribution, Secrets Manager entries, OIDC-federated
IAM role for GitHub Actions.
**Note**: Console work — not a Claude Code task. Step-by-step walkthrough to be written when
you're ready to start it.

## T-DO-5 — CI/CD pipeline

**Goal**: Automate build, test, and deploy on every push to `main`.
**Covers**: DO-10 – DO-14, DO-21
**Scope**: GitHub Actions workflow — test → build & push backend image → run migrations → build
& sync frontend, invalidate CloudFront → update ECS service → smoke-test `/health`.
Authenticates via the OIDC role from T-DO-4.
**Acceptance**:

- Full run succeeds end-to-end on a clean push.
- A deliberately broken test stops the workflow before any deploy step (verify by breaking one
  on purpose, then reverting).
- Both frontend and backend reachable and functioning after a successful run.

## T-DO-6 — Seed script

**Goal**: A repeatable way to populate the production database with demo content.
**Covers**: DO-19, DO-20
**Scope**: Standalone script, separate from test fixtures; no identifier reused from local
fixtures, `task-log.md`, or `decisions.md`.
**Acceptance**:

- Re-running the script does not duplicate rows.
- Includes at least one internal-only comment.

## T-DO-7 (Manual) — Run seed script, verify live

**Goal**: Confirm the deployed app actually looks right to a real visitor.
**Scope**: Run T-DO-6's script by hand against RDS. Verify in a real browser.
**Acceptance**: Log in as a demo account, see seeded requests, confirm the internal-only comment
stays hidden from a non-admin account — verified live, same bar as every other phase.

## T-DO-8 — Terraform codification

**Goal**: Codify the infrastructure T-DO-4 built by hand.
**Covers**: DO-9 (codification half)
**Scope**: Reproduces the console-built resources in Terraform. Likely to split into 3–4 smaller
tasks (network, compute, data/CDN, IAM) once real scope is visible — same pattern as earlier
phases splitting once work started.
**Acceptance**: `terraform plan` against the live infrastructure shows no unintended drift.
