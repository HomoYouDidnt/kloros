# KLoROS Meta-Cognitive Dashboard

Real-time monitoring dashboard for KLoROS's meta-cognitive state, conversation quality, and consciousness metrics.

## Architecture

- **Backend:** FastAPI with WebSocket support (Python)
- **Frontend:** React 18 + Recharts + Tailwind CSS (JavaScript)
- **Data Flow:** KLoROS → State Export Daemon → JSON File → Backend → WebSocket → React Dashboard

## Directory Structure

```
dashboard/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── models.py            # Pydantic data models
│   ├── kloros_bridge.py     # State reader
│   ├── requirements.txt     # Python dependencies
│   └── routes/
│       ├── api.py           # REST API endpoints
│       └── websocket.py     # WebSocket handler
└── frontend/
    ├── src/
    │   ├── App.jsx          # Main dashboard component
    │   └── index.css        # Tailwind styles
    ├── dist/                # Built frontend files
    └── package.json         # Node dependencies
```

## Setup

### 1. Backend Setup

The backend dependencies are already installed in KLoROS's virtual environment:

```bash
cd /home/kloros/dashboard/backend
source /home/kloros/.venv/bin/activate

# Dependencies already installed:
# - fastapi==0.119.0
# - uvicorn==0.37.0
# - pydantic==2.11.9
```

### 2. Frontend Setup

The frontend is already built and ready to serve:

```bash
cd /home/kloros/dashboard/frontend
# Already installed: node_modules/
# Already built: dist/
```

## Running the Dashboard

### Quick Start

Start the backend server:

```bash
cd /home/kloros/dashboard/backend
source /home/kloros/.venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8765
```

The dashboard will be available at:
- **Tailscale:** `http://kloros.tailscale:8765`
- **Local:** `http://localhost:8765`
- **API Docs:** `http://kloros.tailscale:8765/docs`

### Systemd Service (Recommended)

Create `/etc/systemd/system/kloros-dashboard.service`:

```ini
[Unit]
Description=KLoROS Meta-Cognitive Dashboard
Documentation=https://github.com/kloros/dashboard
After=network.target kloros.service
Requires=kloros.service

[Service]
Type=simple
User=kloros
Group=kloros
WorkingDirectory=/home/kloros/dashboard/backend
Environment="PATH=/home/kloros/.venv/bin"
ExecStart=/home/kloros/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8765
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kloros-dashboard.service
sudo systemctl start kloros-dashboard.service
sudo systemctl status kloros-dashboard.service
```

## API Endpoints

### REST API

- `GET /api/health` - Health check
- `GET /api/meta-state` - Current meta-cognitive state
- `GET /api/consciousness` - Current consciousness state
- `GET /api/session` - Session information
- `GET /api/quality-scores` - Quality metrics
- `GET /api/issues` - Current conversation issues
- `GET /api/summary` - Dashboard summary

### WebSocket

- `WS /ws/live` - Real-time updates (1Hz)

## Dashboard Features

### Real-Time Monitoring

1. **Conversation Health** - Overall dialogue quality (0-100%)
2. **Quality Metrics** - Progress, Clarity, Engagement scores
3. **Current Issues** - Repetition, Stuck, Confusion detection
4. **Active Interventions** - Clarify, Change Approach, Summarize, Confirm
5. **Consciousness State** - Valence, Arousal, Uncertainty, Fatigue, Curiosity
6. **Session Info** - Turn count, duration, topics, entities
7. **Quality Timeline** - Live chart of metrics over last minute

### Indicators

- **LIVE** - WebSocket connection status (green = connected)
- **KLoROS ACTIVE** - KLoROS running status (blue = active)

## Data Flow

```
KLoROS Instance
    └─> Meta-Cognitive System (init_meta_cognition)
         └─> State Export Daemon (every 1 second)
              └─> /tmp/kloros_meta_state.json
                   └─> Dashboard Backend (kloros_bridge.py)
                        └─> WebSocket Server
                             └─> React Frontend
```

## Troubleshooting

### Dashboard shows "Waiting for data..."

1. Check if KLoROS is running:
   ```bash
   systemctl status kloros.service
   ```

2. Check if state export daemon started:
   ```bash
   cat /tmp/kloros_meta_state.json
   ```

3. Check if file is being updated:
   ```bash
   watch -n 1 cat /tmp/kloros_meta_state.json
   ```

### WebSocket connection fails

1. Check backend is running:
   ```bash
   systemctl status kloros-dashboard.service
   ```

2. Test WebSocket manually:
   ```bash
   websocat ws://localhost:8765/ws/live
   ```

3. Check firewall (Tailscale should handle this):
   ```bash
   sudo ufw status
   ```

### Backend import errors

Ensure you're in the correct directory and virtual environment:

```bash
cd /home/kloros/dashboard/backend
source /home/kloros/.venv/bin/activate
python3 -c "from main import app; print('OK')"
```

## Development

### Rebuild Frontend

```bash
cd /home/kloros/dashboard/frontend
npm run build
```

### Test Backend

```bash
cd /home/kloros/dashboard/backend
source /home/kloros/.venv/bin/activate
python3 -c "import sys; sys.path.insert(0, '.'); from main import app; print('✓ Backend imports successfully')"
```

### Hot Reload (Development)

Backend:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8765
```

Frontend:
```bash
npm run dev
```

## Security

- **No Authentication** - Dashboard is read-only and only accessible on Tailscale network
- **CORS** - Currently allows all origins (can be restricted to Tailscale subnet)
- **Rate Limiting** - WebSocket updates throttled to 1Hz

## Performance

- **WebSocket:** 1 update per second
- **State File:** Written every 1 second
- **Frontend:** React optimized build (~154KB gzipped)
- **Backend:** Async FastAPI with minimal overhead

## Next Steps

- [ ] Deploy as systemd service
- [ ] Add historical data persistence (SQLite)
- [ ] Implement data export (CSV/JSON)
- [ ] Add configurable alerts/thresholds
- [ ] Multi-session history viewer

## Files Created

### Backend
- `/home/kloros/dashboard/backend/main.py` - FastAPI app
- `/home/kloros/dashboard/backend/routes/api.py` - REST endpoints
- `/home/kloros/dashboard/backend/routes/websocket.py` - WebSocket handler
- `/home/kloros/dashboard/backend/models.py` - Data models
- `/home/kloros/dashboard/backend/kloros_bridge.py` - State reader
- `/home/kloros/dashboard/backend/requirements.txt` - Dependencies

### Frontend
- `/home/kloros/dashboard/frontend/src/App.jsx` - Dashboard UI
- `/home/kloros/dashboard/frontend/src/index.css` - Styles
- `/home/kloros/dashboard/frontend/tailwind.config.js` - Tailwind config
- `/home/kloros/dashboard/frontend/postcss.config.js` - PostCSS config
- `/home/kloros/dashboard/frontend/dist/` - Built files

### KLoROS Integration
- `/home/kloros/src/meta_cognition/state_export.py` - State export daemon
- `/home/kloros/src/meta_cognition/__init__.py` - Updated to start daemon

## License

Part of the KLoROS project.
