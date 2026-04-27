"""FastAPI dashboard — run with:  python dashboard.py
Then open http://<laptop-ip>:8000 on your phone.
"""
from __future__ import annotations
import asyncio
import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pm5_ble import PM5BLE
from workout_recorder import WorkoutRecorder
from metrics import compute
from training_load import workout_tss, compute_history

# ─────────────────────────── paths
BASE     = Path(__file__).parent
STATIC   = BASE / "static"
DATA     = BASE / "data" / "workouts"
SETTINGS = BASE / "data" / "settings.json"
STATIC.mkdir(exist_ok=True)
DATA.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS = {"ftp": 0, "threshold_hr": 175, "rest_hr": 55}

def load_settings() -> dict:
    if SETTINGS.exists():
        return {**DEFAULT_SETTINGS, **json.loads(SETTINGS.read_text())}
    return DEFAULT_SETTINGS.copy()

def save_settings(s: dict) -> None:
    SETTINGS.write_text(json.dumps(s, indent=2))

# ─────────────────────────── app
app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC), name="static")

pm5      = PM5BLE()
recorder = WorkoutRecorder()
_clients: set[WebSocket] = set()

# ─────────────────────────── broadcast
async def broadcast(msg: dict) -> None:
    dead = set()
    payload = json.dumps(msg)
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _clients -= dead

# ─────────────────────────── BLE callbacks
def _on_force(seq: int, values: list[float]) -> None:
    stroke = recorder.on_force_packet(seq, values)
    if stroke:
        asyncio.create_task(broadcast({
            "event": "stroke",
            "data": {
                "index":   stroke.index,
                "peak":    stroke.peak_force,
                "ttp":     stroke.time_to_peak_pct,
                "hr":      stroke.hr,
                "rate":    recorder.stroke_rate,
                "elapsed": round(recorder.duration),
                "watts":   stroke.watts,
                "split":   stroke.split,
            },
        }))

def _on_stroke(data: dict) -> None:
    recorder.on_stroke_data(data)

def _on_hr(hr: int) -> None:
    recorder.on_hr(hr)
    asyncio.create_task(broadcast({"event": "hr", "data": {"hr": hr}}))

# ─────────────────────────── HTTP routes
@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")

# ── Workouts
@app.get("/api/workouts")
async def list_workouts():
    settings = load_settings()
    files    = sorted(DATA.glob("*.json"), reverse=True)
    result   = []
    for f in files[:50]:
        try:
            d   = json.loads(f.read_text())
            m   = d.get("metrics", {})
            tss, method = workout_tss(m, settings)
            result.append({
                "id":           f.stem,
                "date":         d.get("date", ""),
                "stroke_count": m.get("stroke_count", 0),
                "duration":     m.get("duration", 0),
                "tss":          tss,
                "tss_method":   method,
            })
        except Exception:
            pass
    return JSONResponse(result)

@app.get("/api/workouts/{wid}")
async def get_workout(wid: str):
    path = DATA / f"{wid}.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return JSONResponse(json.loads(path.read_text()))

# ── Settings
@app.get("/api/settings")
async def get_settings():
    return JSONResponse(load_settings())

class Settings(BaseModel):
    ftp:          int = 0
    threshold_hr: int = 175
    rest_hr:      int = 55

@app.post("/api/settings")
async def post_settings(s: Settings):
    data = {"ftp": s.ftp, "threshold_hr": s.threshold_hr, "rest_hr": s.rest_hr}
    save_settings(data)
    return JSONResponse({"ok": True})

# ── Training load history
@app.get("/api/training-load")
async def training_load():
    settings = load_settings()
    files    = sorted(DATA.glob("*.json"))
    workouts = []
    for f in files:
        try:
            d = json.loads(f.read_text())
            workouts.append({"date": d.get("date", ""), "metrics": d.get("metrics", {})})
        except Exception:
            pass
    history = compute_history(workouts, settings)
    return JSONResponse(history)

# ─────────────────────────── WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    await ws.send_text(json.dumps({
        "event": "status",
        "data":  {"connected": pm5.is_connected},
    }))
    try:
        while True:
            raw = await ws.receive_text()
            await _handle(json.loads(raw), ws)
    except WebSocketDisconnect:
        _clients.discard(ws)

async def _handle(msg: dict, ws: WebSocket) -> None:
    action = msg.get("action")

    if action == "scan":
        await ws.send_text(json.dumps({"event": "scanning"}))
        devices = await pm5.scan()
        await ws.send_text(json.dumps({"event": "devices", "data": devices}))

    elif action == "connect":
        pm5.set_callbacks(on_force=_on_force, on_stroke=_on_stroke, on_hr=_on_hr)
        ok = await pm5.connect(msg.get("address", ""))
        await broadcast({"event": "connected" if ok else "connect_failed"})

    elif action == "disconnect":
        await pm5.disconnect()
        await broadcast({"event": "disconnected"})

    elif action == "start":
        recorder.start()
        await broadcast({"event": "workout_started"})

    elif action == "stop":
        recorder.stop()
        m        = compute(recorder)
        settings = load_settings()
        tss, tss_method = workout_tss(m, settings)
        wid  = datetime.now().strftime("%Y%m%d_%H%M%S")
        data = {
            "id":         wid,
            "date":       datetime.now().isoformat(),
            "tss":        tss,
            "tss_method": tss_method,
            "metrics":    m,
            "strokes": [
                {
                    "index":        s.index,
                    "force_curve":  s.force_curve,
                    "peak_force":   s.peak_force,
                    "time_to_peak": s.time_to_peak_pct,
                    "elapsed_time": s.elapsed_time,
                    "distance":     s.distance,
                    "hr":           s.hr,
                    "watts":        s.watts,
                    "split":        s.split,
                }
                for s in recorder.strokes
            ],
        }
        (DATA / f"{wid}.json").write_text(json.dumps(data, indent=2))
        await broadcast({"event": "results", "data": m, "tss": tss,
                         "tss_method": tss_method, "workout_id": wid})

# ─────────────────────────── entry point
if __name__ == "__main__":
    import uvicorn
    import socket
    ip = socket.gethostbyname(socket.gethostname())
    print(f"\n  Dashboard: http://{ip}:8000")
    print(f"  Open that URL on your phone (same Wi-Fi)\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
