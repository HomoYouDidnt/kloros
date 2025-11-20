"""
KLoROS Dashboard Backend

FastAPI application providing REST API and WebSocket endpoints
for real-time meta-cognitive state monitoring.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8765
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
from pathlib import Path

# Import routes
from routes import api, websocket

# Create FastAPI app
app = FastAPI(
    title="KLoROS Dashboard API",
    description="Real-time meta-cognitive monitoring for KLoROS",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configure CORS for Tailscale network
# Allow all origins for now (can be restricted to Tailscale subnet later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict to Tailscale subnet
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api.router)
app.include_router(websocket.router)


@app.get("/")
async def root():
    """Root endpoint - serve React app or API info."""
    # Check if frontend build exists
    frontend_build = Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    
    if frontend_build.exists():
        return FileResponse(frontend_build)
    else:
        return {
            "service": "KLoROS Dashboard API",
            "version": "1.0.0",
            "status": "running",
            "endpoints": {
                "api": "/api/meta-state",
                "websocket": "/ws/live",
                "docs": "/docs"
            },
            "note": "Frontend not built yet. Build React app and it will be served here."
        }


# Serve React frontend static files (when built)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")


@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    print("="*60)
    print("KLoROS Dashboard Backend Starting")
    print("="*60)
    print(f"API Docs: http://localhost:8765/docs")
    print(f"WebSocket: ws://localhost:8765/ws/live")
    print(f"Meta-State: http://localhost:8765/api/meta-state")
    print("="*60)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print("[dashboard] Shutting down...")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8765,
        reload=False,
        log_level="info"
    )
