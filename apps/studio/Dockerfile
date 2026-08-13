# Shared file for both the `client-web` (dev server) and `client-web-prod`
# (static export served via `npx serve`) compose services — build-stage-selected
# via `target:` in docker-compose.yml. Spec: cirq-studio-tooling.md Requirement 7.

FROM node:20-slim AS base
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# `client-web`: runs the existing Expo dev server (docker-compose.yml supplies the
# `npx expo start --web --port 8081` command; this stage just needs deps + source).
FROM base AS dev
EXPOSE 8081

# `client-web-prod`: builds the static web export, then serves it — verifies the
# production build actually works, independent of the dev server (Requirement 7).
FROM base AS prod
RUN npx expo export --platform web
EXPOSE 8082
CMD ["npx", "serve", "dist", "-l", "8082"]
