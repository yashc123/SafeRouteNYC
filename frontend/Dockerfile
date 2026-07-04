# Multi-stage: build the static frontend with Vite, then serve it with nginx
# (which also reverse-proxies /api to the backend). Build context is ./frontend.

# --- build stage ---------------------------------------------------------
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

# Vite bakes VITE_* vars into the bundle AT BUILD TIME. These come from the
# docker-compose build args; we surface them as env vars for `npm run build`.
ARG VITE_API_URL=/api
ARG VITE_MAPTILER_KEY
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_MAPTILER_KEY=$VITE_MAPTILER_KEY
RUN npm run build

# --- serve stage ---------------------------------------------------------
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
# nginx:alpine's default CMD runs the server.
