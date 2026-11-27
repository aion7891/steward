# Steward web UI image: build the React app with Node, then serve it with nginx.
# Stage 1 never ships; the final image only contains nginx and the built files.

# ---------- Stage 1: build ----------
FROM node:22.16.0-alpine AS build
WORKDIR /app

# Install exact dependency versions from the lock file (cached unless they change)
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# Build the static site into /app/dist
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

# ---------- Stage 2: serve ----------
# The "unprivileged" nginx image runs as a normal user and listens on port 8080
FROM nginxinc/nginx-unprivileged:1.27.5-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
