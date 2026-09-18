# syntax=docker/dockerfile:1

# Static-file server for the local prod-like stack (T-DO-3).
#
# In production the frontend is S3 + CloudFront (design.md decision 3): no
# server, no container, just the files. This image is the local stand-in for
# that pair, and it is deliberately a separate Dockerfile in a separate
# directory rather than a stage added to frontend/Dockerfile:
#
#  1. T-DO-2's image has to stay unrunnable. It ends at `FROM scratch` with no
#     Cmd, no Entrypoint and no port, so `docker run` on it fails with "no
#     command specified" — "a build tool, not a runtime" is a property there,
#     not a comment, and a serving stage bolted onto it would quietly demote it
#     to the latter. This file consumes that image *as a build stage* instead,
#     which is also what makes the bytes served below provably the bytes that
#     image holds: not a rebuild, not a second `npm run build`, not a copy of
#     the source tree.
#  2. It lives outside frontend/ because every tracked file under frontend/ is
#     an input to the Tailwind build (T-DO-2's measurement, now DO-26). A
#     Dockerfile placed there would change the emitted stylesheet merely by
#     existing — an unacceptable side effect for a task whose whole job is
#     verifying the artifacts the earlier tasks built.
#
# Built by docker-compose.prod.yml. The dist image it reads must already exist
# locally; deploy/README.md has the one command that produces it.

ARG FRONTEND_DIST_IMAGE=service-portal-frontend-dist:local

# Stage one is T-DO-2's output image itself. It contains dist/ at its root and
# nothing else — no shell, no base layer — which is all COPY needs.
FROM ${FRONTEND_DIST_IMAGE} AS dist

FROM nginx:1.29-alpine AS serve

# Replaces the stock default.conf rather than adding beside it: two server
# blocks listening on 80 would make which one answers a matter of ordering.
COPY nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=dist / /usr/share/nginx/html
