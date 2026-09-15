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

## T-DO-2 — Frontend Dockerfile (build stage only)

**Goal**: A reproducible build of the frontend static assets.
**Covers**: DO-2
**Scope**: Multi-stage Docker build producing `dist/`; no server runs inside the image — it's a
build tool, not a runtime.
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
