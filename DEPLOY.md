# SafeRouteNYC — Production Deployment (single EC2 instance, Docker Compose)

The whole stack — **PostGIS + Redis + FastAPI backend + built frontend (nginx)** —
runs on one machine via `docker-compose.prod.yml`, served at **one URL on port 80**.
Local dev (`docker-compose.yml` + `npm run dev`) is unchanged and still works.

## How it fits together
- **nginx** (the `frontend` image) serves the built React app and reverse-proxies
  `/api/*` to the backend, so the app is a single origin (no CORS).
- **Frontend build-time env:** Vite bakes `VITE_*` into the static bundle when the
  image is built. `docker-compose.prod.yml` passes them as build args
  (`VITE_API_URL=/api`, `VITE_MAPTILER_KEY=...`) → the Dockerfile sets them as env
  → `npm run build`. The MapTiler key is public (restrict it by domain); the
  **Anthropic key never reaches the frontend** — the agent runs on the backend.
- **Backend** and **db/redis** have **no published ports** — only nginx is exposed.
- **Data:** the backend image also contains the `data/` pipeline, so the empty
  production DB gets populated by running the pipeline *inside* the backend
  container (below). The ~71 MB graph cache is downloaded on the server at load
  time (it's not in the repo).

## Instance sizing
Use ≥ **t3.medium (2 vCPU / 4 GB)**. The ingestion step pulls ~340k crime rows
into memory, and the backend holds the street graph + KD-tree in RAM. Give the
root volume ~20 GB.

---

## Runbook — fresh Ubuntu EC2 → running app

### 0. EC2 security group
Open inbound **80** (HTTP) and **22** (SSH) to your IP. SSH in.

### 1. Install Docker + Compose plugin
```bash
sudo apt-get update && sudo apt-get install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker            # apply the docker group to this shell (or log out/in)
docker compose version   # confirm the compose plugin is present
```

### 2. Clone the repo
```bash
git clone https://github.com/<you>/SafeRouteNYC.git
cd SafeRouteNYC
```

### 3. Create and fill in the production env
```bash
cp .env.prod.example .env.prod
nano .env.prod
```
Set real values — at minimum:
- `POSTGRES_PASSWORD` **and** the matching password inside `DATABASE_URL`
- `ANTHROPIC_API_KEY`, `MAPTILER_KEY`, `VITE_MAPTILER_KEY`
- `CORS_ORIGINS` → `http://<your-public-ip-or-domain>`
Leave `DATABASE_URL` host as `db`, `REDIS_URL` host as `redis`, `VITE_API_URL=/api`.

### 4. Build and start the stack
```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```
First build takes a few minutes (installs Python deps, builds the frontend).
The backend comes up healthy immediately; `/api/route` returns 503 until data is loaded.

### 5. Load the data (one-time, ~10–15 min)
```bash
bash deploy/load-data.sh
```
This runs the three pipeline steps in the backend container (graph → NYC data →
scoring) and restarts the backend. (Equivalent manual commands are in that script.)

### 6. Verify
```bash
curl http://localhost/api/health          # {"status":"ok"}
curl http://localhost/api/graph/stats      # ~36k nodes / ~115k edges
```
Then open **`http://<your-ec2-public-ip>/`** in a browser — the map loads, routing,
Explore, and the Ask box all work.

---

## Day-2 operations
```bash
C="docker compose --env-file .env.prod -f docker-compose.prod.yml"
$C ps                    # status
$C logs -f backend       # tail backend logs
$C restart backend       # restart just the API
$C down                  # stop (keeps the pgdata volume / your data)
$C up -d --build         # after `git pull`, rebuild + restart
```
- **Refresh the safety data** later: re-run `bash deploy/load-data.sh`.
- **HTTPS:** out of scope here (the stack serves plain HTTP on :80). For TLS, put a
  Caddy/Traefik or an ALB in front, or add certbot — none of that changes the app.
- **Secrets:** `.env.prod` is gitignored — never commit it.
