# Phase 4 — DevOps & Cloud Deployment: Requirements

EARS-style, prefixed `DO-N`.

## Containerization

- **DO-1**: The backend shall run as a Docker container built from a `Dockerfile` checked into
  the repo.
- **DO-2**: The frontend build shall be produced via a Docker build stage, even though the
  deployed artifact is static files — so the build is reproducible outside any one developer's
  machine.
- **DO-3**: The backend container shall read all environment-specific config (DB connection
  string, JWT secret, `FRONTEND_ORIGIN`) from environment variables injected at runtime; none
  shall be baked into the image.
- **DO-4**: The backend container shall write all logs to `stdout`/`stderr`; the application
  shall not write to a local log file.
- **DO-23**: Dependency manifests (`requirements.txt` for the backend, `package-lock.json` for
  the frontend) shall pin exact resolved versions, including transitive dependencies, so that
  two builds from the same commit produce identical dependency sets regardless of when they run.

## Infrastructure

- **DO-5**: The backend shall run on ECS Fargate behind an Application Load Balancer, in a VPC
  with public subnets and a security group restricting inbound traffic to the ALB only.
- **DO-6**: The database shall run on RDS for PostgreSQL, not as a container.
- **DO-7**: The frontend build output shall be served from an S3 bucket via a CloudFront
  distribution.
- **DO-8**: `JWT_SECRET_KEY` and database credentials shall be stored in AWS Secrets Manager and
  injected into the ECS task definition; they shall never appear in the repo, the Docker image,
  or GitHub Actions logs.
- **DO-9**: The infrastructure shall be provisioned manually via the AWS Console initially; a
  Terraform configuration reproducing it shall be written as a subsequent codification step, not
  a deployment prerequisite.

## CI/CD

- **DO-10**: A GitHub Actions workflow shall run on every push to `main`.
- **DO-11**: The workflow shall run the backend test suite and the Playwright suite; a failure
  shall stop the workflow before any build or deploy step runs.
- **DO-12**: The workflow shall build the backend image, tag it with the git commit SHA, and
  push it to ECR.
- **DO-13**: The workflow shall build the frontend, sync the output to S3, and invalidate the
  CloudFront cache.
- **DO-14**: The workflow shall register a new ECS task definition revision pointing at the
  pushed image and update the ECS service to use it.
- **DO-15**: The workflow shall smoke-test the `/health` endpoint after deployment and shall
  fail the workflow if that check fails.
- **DO-21**: The workflow shall run Alembic migrations against the production database as an
  automated step — unlike `JWT_SECRET_KEY` provisioning and demo seeding, migrations run on
  nearly every backend change, and forgetting one before deploying dependent code is a common,
  easy-to-hit outage.

## Environments

- **DO-16**: Local Docker Compose remains the sole non-production environment; no second AWS
  environment is provisioned in this phase.
- **DO-17**: Differences between local and production config shall be environment-variable-driven,
  with no code branching on environment name.

## Data

- **DO-18**: The production database schema shall be created by running the repo's existing
  Alembic migrations directly against RDS — never by copying schema or data from the local
  development database.
- **DO-19**: A dedicated seed script, separate from test fixtures, shall populate the production
  database with clearly-fake demo data: demo accounts, a handful of sample service requests
  spanning multiple statuses and priorities, and at least one internal-only comment
  (demonstrating `CM-7`/`CM-8`'s role gating live). The script shall be idempotent.
- **DO-20**: Demo account credentials shall be freshly generated and shall never reuse an email,
  password, or identifier already present in the local test fixtures, `task-log.md`, or
  `decisions.md`.

## Health & Observability

- **DO-22**: The backend shall expose `GET /health`, unauthenticated, returning 200 only if a
  live database round-trip succeeds. Used by the deployment pipeline's smoke test (`DO-15`) and
  by the ALB target group's own health checks.
