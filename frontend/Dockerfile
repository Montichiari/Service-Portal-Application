# syntax=docker/dockerfile:1

# Frontend build image (T-DO-2; DO-2, DO-23, DO-25).
#
# This is a build tool, not a runtime. The deployed artifact is static files on
# S3 behind CloudFront (design.md decision 3), so nothing here serves anything:
# the final stage is `scratch` holding `dist/` alone, and the way to use it is
#
#     docker build --output type=local,dest=out frontend
#
# which writes the built assets to `out/` without ever starting a container. A
# `docker build -t` of this file produces an image you cannot run, and that is
# the intended shape — if something is ever wanted to serve these files
# (T-DO-3's prod-like stack), it belongs in its own image serving this one's
# output, not bolted on here as a stage that quietly makes this a runtime.
#
# Node is pinned to the exact patch version the project is developed against
# (v26.5.0), same reasoning as backend/Dockerfile's 3.14-slim: a build running
# a different toolchain than the developer's machine is a difference that only
# ever surfaces in production. npm is the one piece that does differ — 11.17.0
# here against 12.0.1 on the dev machine, because npm ships inside the Node
# image and cannot be pinned independently without installing a second copy.
# It does not reach the output: `npm ci` installs what package-lock.json
# resolves either way, and the evidence is that this image's dist/ is
# byte-identical to a local `npm run build` — every file, hash-bearing name
# included. That equality is the acceptance criterion, and it is checked by
# diffing the two trees, not by watching the build succeed.
ARG NODE_VERSION=26.5.0-bookworm-slim

# --- build -------------------------------------------------------------------
FROM node:${NODE_VERSION} AS build

# DO-25. Vite inlines `import.meta.env.VITE_*` into the bundle at build time —
# it is not runtime config the way the backend's DATABASE_URL is (DO-3), so
# this build argument is the only point at which the deployed frontend can be
# aimed at the real backend. The default is the value frontend/.env carries, so
# a plain `docker build` with no --build-arg reproduces the local build exactly;
# T-DO-5 passes the ALB URL here instead:
#
#     docker build --build-arg VITE_API_URL=https://api.example.com ...
#
# Deliberately an ARG promoted to ENV rather than a copied .env file.
# .dockerignore keeps every .env out of the context, so there is exactly one
# place the value can come from and a developer's uncommitted local file cannot
# change what an image contains. Vite's own precedence (process env beats a
# .env file) would have made a copied file harmless-but-losing; leaving it in
# would still mean two sources for one setting, which is the thing DO-25 is
# about.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

WORKDIR /app

# Dependencies ahead of source, so editing a component does not reinstall the
# tree. `npm ci` rather than `npm install`: ci installs exactly what
# package-lock.json resolves and fails outright if the lockfile disagrees with
# package.json, where install is free to re-resolve a `^` range to whatever is
# newest today. That is DO-23's frontend half — the lockfile already pins
# transitive versions, and this is the command that actually honours them.
COPY package.json package-lock.json ./
RUN npm ci

# The whole tracked tree, minus .dockerignore's exclusions — and "whole" is
# load-bearing, not lazy. `npm run build` is `tsc -b && vite build`:
# tsconfig.json's project references reach src/e2e/ and playwright.config.ts as
# well as the app, so typechecking those is part of the build; and Tailwind v4
# detects its sources by walking the project rather than from a `content`
# array, which makes every tracked file — documentation included — an input to
# the emitted stylesheet. .dockerignore has the measurements; the short version
# is that narrowing this COPY silently changes the CSS.
COPY . .

RUN npm run build

# --- dist --------------------------------------------------------------------
# Nothing but the build output: no node_modules, no source, no shell, no base
# layer at all.
FROM scratch AS dist
COPY --from=build /app/dist /
