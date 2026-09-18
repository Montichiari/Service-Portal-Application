# The local prod-like stack (T-DO-3)

`docker-compose.prod.yml` at the repo root runs the images `T-DO-1` and
`T-DO-2` build, together, on one machine: Postgres, `alembic upgrade head`,
the FastAPI image, and the built frontend behind nginx. Nothing mounts source,
nothing reloads, and no dev server is involved. It exists to answer one
question before `T-DO-4` touches AWS — do the built artifacts actually work
together — and it is not production: the database is a container rather than
RDS, nginx stands in for S3 + CloudFront, and there is no ALB, TLS or Secrets
Manager.

## Running it

From the repo root, three steps. Only the first is unusual:

```powershell
# 1. Build the frontend dist image, pinned to this stack's API port.
#    VITE_API_URL is baked into the bundle at build time (DO-25), so it is a
#    property of the artifact, not of the container that serves it — which is
#    why compose cannot build this one for you.
docker build --build-arg VITE_API_URL=http://localhost:8001 `
    -t service-portal-frontend-dist:local frontend

# 2. A signing secret. The stack has no committed default for it on purpose
#    (see below); compose refuses to start without one. Either export it:
$env:JWT_SECRET_KEY = (python -c "import secrets; print(secrets.token_urlsafe(48))")
#    or put JWT_SECRET_KEY=... in a .env file at the repo root, which compose
#    reads automatically and .gitignore already excludes.

# 3. Up.
docker compose -f docker-compose.prod.yml up -d --build
```

In bash the same three, with `\` continuations and
`export JWT_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(48))')`.

Then:

| URL                           | What                                              |
| ----------------------------- | ------------------------------------------------- |
| http://localhost:8080         | the portal — nginx serving the built `dist/`       |
| http://localhost:8001/health  | the API's readiness probe (DO-22)                  |
| http://localhost:8001/docs    | Swagger UI, same image, same document              |

Tear down with `docker compose -f docker-compose.prod.yml down`, or
`down -v` to discard the stack's database as well.

## Why the ports are 8001 and 8080

The development backend owns `:8000` and Vite owns `:5173`. Keeping off both
lets the two stacks run side by side, but the real reason is sharper: if this
stack published `:8000`, a browser pointed at it could be answered by the
development backend, and **nothing on the page would look wrong**. A prod-like
check that silently talks to a dev server proves nothing. This is not
hypothetical — while `T-DO-3` was being verified, the process listening on
`:8000` was a uvicorn started before `T-DO-0`, still serving the old
memory-only `/health`.

The same reasoning gives the compose project its own name
(`name: service-portal-prod`). Without it, compose derives the project from
the directory, and this file's `db` service would collide with the development
stack's — same project, same service name, different definition — so starting
one would recreate the other's container and adopt its volume.

## Why the frontend is two images

`frontend/Dockerfile` ends at `FROM scratch`: it holds `dist/` and nothing
else, has no `Cmd` and no `Entrypoint`, and `docker run` on it fails with "no
command specified". That is `T-DO-2`'s deliberate shape — a build tool, not a
runtime — and adding a serving stage there would have quietly ended it.

So `frontend.Dockerfile` here consumes that image *as a build stage*
(`FROM ${FRONTEND_DIST_IMAGE}`) and copies its contents into nginx. The bytes
served are therefore provably the bytes that image holds: not a rebuild, not a
second `npm run build`, not a copy of the source tree. It lives in `deploy/`
rather than in `frontend/` because every tracked file under `frontend/` is an
input to the Tailwind build (`DO-26`) — a Dockerfile placed there would change
the emitted stylesheet merely by existing.

If step 1 is skipped, step 3 fails at the `web` build with
`pull access denied, repository does not exist` — Docker looking for
`service-portal-frontend-dist:local` in a registry, because it is not on the
machine. That message is about the missing local tag, not about credentials.

## Why `JWT_SECRET_KEY` has no default

Every other value in the compose file is a throwaway local (the Postgres
credentials, the origin, the ports). The signing key is the one value where a
committed default would be the Phase 3 gap all over again —
`.env.example`'s `change-me-to-a-long-random-secret` is live in development,
so every token that instance issues is forgeable by anyone who has read the
repo. In the deployed stack this comes from Secrets Manager (DO-8); here it
comes from the environment, which is the same shape of answer, and compose
refuses to start without it.

Keep it stable between runs if you want a browser session to survive a
restart: tokens signed by the old key stop validating when the key changes.
