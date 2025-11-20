# KLoROS Modern Dashboard Architecture

**Status:** 🚧 IN PROGRESS
**Created:** November 1, 2025
**Purpose:** Real-time meta-cognition and system monitoring dashboard

---

## Tech Stack

### Backend
- **FastAPI** - Modern async Python web framework
- **WebSocket** - Real-time bidirectional communication
- **Uvicorn** - ASGI server
- **SQLite** - Query meta-cognition state directly from KLoROS memory

### Frontend
- **React 18** - Component-based UI
- **Vite** - Fast build tool and dev server
- **Recharts** - Beautiful, responsive charts
- **Tailwind CSS** - Utility-first styling
- **WebSocket API** - Live data streaming

### Deployment
- **Backend Port:** 8765 (accessible on Tailscale network)
- **Frontend:** Static files served by FastAPI
- **Single binary deployment** via systemd

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Browser (Any Device)                         │
│                   http://kloros.tailscale:8765                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP/WebSocket
                            ▼
                ┌───────────────────────┐
                │   FastAPI Server      │
                │   (Port 8765)         │
                │                       │
                │  ┌─────────────────┐  │
                │  │ REST API        │  │  /api/meta-state
                │  │ Endpoints       │  │  /api/consciousness
                │  └─────────────────┘  │  /api/history
                │                       │
                │  ┌─────────────────┐  │
                │  │ WebSocket       │  │  /ws/live
                │  │ Live Updates    │  │  (push every 1s)
                │  └─────────────────┘  │
                └───────────┬───────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │   KLoROS Instance     │
                │                       │
                │  • meta_bridge        │
                │  • consciousness      │
                │  • memory_enhanced    │
                │  • conversation_flow  │
                └───────────────────────┘
```

---

## Data Flow

### 1. Real-Time Updates (WebSocket)

```python
# Every 1 second, push to connected clients:
{
  "type": "meta_state",
  "timestamp": "2025-11-01T21:30:45Z",
  "conversation_health": 0.85,
  "quality_scores": {
    "progress": 0.9,
    "clarity": 0.8,
    "engagement": 0.85
  },
  "issues": {
    "repetition": false,
    "stuck": false,
    "confusion": false
  },
  "interventions": {
    "clarify": false,
    "change_approach": false,
    "summarize": false
  },
  "affect": {
    "valence": 0.3,
    "arousal": 0.2,
    "uncertainty": 0.4
  },
  "session": {
    "turn_count": 12,
    "duration_seconds": 145
  }
}
```

### 2. Historical Data (REST API)

```python
GET /api/history?hours=24
{
  "samples": [
    {"ts": "...", "conversation_health": 0.85, ...},
    ...
  ],
  "summary": {
    "avg_health": 0.78,
    "interventions_triggered": 5,
    "total_turns": 234
  }
}
```

---

## Dashboard Components

### Page Layout

```
┌──────────────────────────────────────────────────────────────┐
│  KLoROS Meta-Cognitive Dashboard            🟢 LIVE          │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │ Conversation Health │  │   Current Issues             │  │
│  │                     │  │                              │  │
│  │      ⭕ 85%        │  │   ✅ No issues detected      │  │
│  │   ████████░░       │  │                              │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Quality Metrics (Live)                             │   │
│  │                                                       │   │
│  │   Progress  █████████░ 90%                          │   │
│  │   Clarity   ████████░░ 80%                          │   │
│  │   Engage    █████████░ 85%                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Quality Timeline (Last Hour)                       │   │
│  │                                                       │   │
│  │   [Line chart showing progress/clarity over time]    │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │ Consciousness       │  │  Recent Interventions        │  │
│  │                     │  │                              │  │
│  │ Valence:   +0.3    │  │  21:30 Clarified response    │  │
│  │ Arousal:   +0.2    │  │  21:25 Changed approach      │  │
│  │ Uncertain:  0.4    │  │  21:20 No intervention       │  │
│  └─────────────────────┘  └──────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │   Session Stats                                       │   │
│  │                                                       │   │
│  │   Turns: 12  |  Duration: 2m 25s  |  Topics: 3      │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## Backend API Specification

### REST Endpoints

#### `GET /api/meta-state`
Current meta-cognitive state snapshot.

**Response:**
```json
{
  "conversation_health": 0.85,
  "quality_scores": {...},
  "issues": {...},
  "interventions": {...},
  "affect": {...}
}
```

#### `GET /api/history?hours=24&metric=conversation_health`
Historical meta-cognition data.

**Response:**
```json
{
  "samples": [
    {"timestamp": "...", "value": 0.85},
    ...
  ]
}
```

#### `GET /api/consciousness`
Current consciousness state.

**Response:**
```json
{
  "affect": {
    "valence": 0.3,
    "arousal": 0.2,
    "uncertainty": 0.4
  },
  "needs": {...},
  "emotions": [...]
}
```

#### `GET /api/session`
Current conversation session info.

**Response:**
```json
{
  "turn_count": 12,
  "duration_seconds": 145,
  "topics": ["audio", "GPU", "memory"],
  "entities": ["RTX 3080", "PulseAudio"]
}
```

### WebSocket Endpoint

#### `WS /ws/live`
Real-time updates pushed every 1 second.

**Message Format:**
```json
{
  "type": "update",
  "data": {
    "meta_state": {...},
    "consciousness": {...},
    "session": {...}
  }
}
```

---

## Frontend Components

### React Component Tree

```
<App>
  ├── <Header>
  ├── <DashboardGrid>
  │   ├── <ConversationHealthWidget>
  │   ├── <CurrentIssuesWidget>
  │   ├── <QualityMetricsWidget>
  │   ├── <QualityTimelineChart>
  │   ├── <ConsciousnessWidget>
  │   ├── <InterventionsLogWidget>
  │   └── <SessionStatsWidget>
  └── <WebSocketProvider>
```

### Key Features

1. **Live Updates** - WebSocket connection auto-reconnects
2. **Responsive Design** - Works on mobile, tablet, desktop
3. **Dark Mode** - Easy on the eyes for monitoring
4. **Historical View** - Toggle between live and historical data
5. **Export** - Download metrics as CSV/JSON

---

## Directory Structure

```
/home/kloros/dashboard/
├── backend/
│   ├── main.py              # FastAPI app
│   ├── routes/
│   │   ├── api.py           # REST endpoints
│   │   └── websocket.py     # WebSocket handler
│   ├── models.py            # Data models
│   └── kloros_bridge.py     # Interface to KLoROS instance
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── ConversationHealthWidget.jsx
│   │   │   ├── QualityMetricsWidget.jsx
│   │   │   ├── QualityTimelineChart.jsx
│   │   │   └── ...
│   │   └── hooks/
│   │       └── useWebSocket.js
│   ├── package.json
│   └── vite.config.js
└── dashboard.service         # systemd service
```

---

## Deployment

### systemd Service

```ini
[Unit]
Description=KLoROS Dashboard
After=kloros.service

[Service]
Type=simple
User=kloros
WorkingDirectory=/home/kloros/dashboard/backend
ExecStart=/home/kloros/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8765
Restart=always

[Install]
WantedBy=multi-user.target
```

### Tailscale Access

Dashboard accessible at: `http://kloros.tailscale:8765`

Or via Tailscale IP: `http://100.x.x.x:8765`

---

## Security

- **No Authentication** (Tailscale network only - trusted devices)
- **Read-Only** - Dashboard cannot modify KLoROS state
- **CORS** - Restricted to Tailscale subnet
- **Rate Limiting** - WebSocket updates throttled to 1Hz

---

## Next Steps

1. ✅ Architecture design
2. ⏳ Build FastAPI backend
3. ⏳ Create React frontend
4. ⏳ Implement WebSocket bridge
5. ⏳ Deploy and test
6. ⏳ Add historical data persistence

---

**Status:** Ready to implement backend
