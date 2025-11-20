# KLoROS D-REAM Dashboard

Local web dashboard to review & approve D-REAM improvements and queue experiments. Optimized for
access on your Tailscale network.

## Quick Start (Docker Compose)
```bash
cd kloros-dream-dashboard
echo AUTH_TOKEN=super-secret-token > .env    # optional: create
docker compose --env-file .env up --build -d
# App listens on 0.0.0.0:8080 inside the container; host publishes :8080
# Visit: http://<your-tailscale-ip>:8080
```
To approve/decline/queue via the UI, set your token in the browser dev console:
```js
localStorage.setItem('AUTH_TOKEN', 'super-secret-token')
```
(HTMX forms will include it automatically.)

## Endpoints (for integrations)
- `GET /api/pending` → list pending improvements
- `POST /api/approve/{id}` (Bearer token) → approve
- `POST /api/decline/{id}` (Bearer token) → decline
- `GET /api/queue?status=queued|running|…` → list queue
- `POST /api/queue` (form-data; Bearer token) → add item
  - fields: `type_key`, `params_json` (JSON), `note`
- `POST /api/queue/{id}/status` (JSON; Bearer token) → update status
- `GET /api/experiment-types` → list types
- `GET /events` → Server-Sent Events channel (SSE) for live updates

## Static IP / Tailscale
- The app binds on `0.0.0.0:8080` in the container; host publishes `:8080`.
- On your Tailscale node (e.g., ASTRAEA), access via its Tailscale IP: `http://<node-ip>:8080`.
- Use Tailscale ACLs to restrict who can reach the node/port.
- Optionally, layer HTTP auth by setting `AUTH_TOKEN` (already enforced by the API/HTMX actions).

## Data & Config
- SQLite path: `./data/dream.db` (mounted to `/data/dream.db`).
- Experiment types JSON: `./data/experiment_types.json`. Edit to add/remove experiment types.
- On first run, seed data is created.

## Swapping to React later
This project keeps the UI light (HTMX + Tailwind). If you want a React/Next.js frontend later,
you can point it at these API endpoints or mount `/static` for a SPA. The backend will remain
unchanged.

## Integrating with D-REAM
Wire your D-REAM runner to:
- push candidate improvements into the `improvements` table (via the DB or a small POST you add),
- poll the queue for new experiments, and
- update statuses via `/api/queue/{id}/status`.



## Sidecar
A small companion service that:
- Publishes D-REAM candidates via `POST /api/improvements`
- Claims jobs with `POST /api/queue/claim` and runs them
- Reports status via `POST /api/queue/{id}/status`

### Usage
```bash
docker compose up -d --build
# Ensure AUTH_TOKEN is set in .env for both services
```
Env:
- `AUTH_TOKEN` shared with dashboard
- `DASH_URL` internal service URL (default `http://d_ream_dashboard:8080`)
- `WORKER_ID` identifier for claim records
Mount `/var/log/dream` if you want the sidecar to tail `candidates.jsonl` from D-REAM.
