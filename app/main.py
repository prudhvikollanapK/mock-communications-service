import asyncio
import json
import time
import uuid
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.config import (
    DEFAULT_CONCURRENT_LIMIT, DEFAULT_CPS_LIMIT, RECORDING_DIR
)
from app.database import Base, engine, get_db
from app.models import CallRecord, ApiKeyConfig
from app.redis_client import (
    redis_client, RESERVE_CALL_LUA, active_key_for, cps_key_for
)
from app.schemas import CreateCallRequest, CreateCallResponse, CallResponse, MetricsResponse
from app.security import require_api_key, hash_api_key
from app.tasks import progress_call

app = FastAPI(title="Mock Communications Service", version="1.0.0")

@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    Path(RECORDING_DIR).mkdir(parents=True, exist_ok=True)

@app.get("/health")
async def health():
    await redis_client.ping()
    return {"status": "ok"}

def get_limits(db: Session, key_hash: str) -> tuple[int, int]:
    config = db.get(ApiKeyConfig, key_hash)
    if config:
        return config.concurrent_limit, config.cps_limit
    return DEFAULT_CONCURRENT_LIMIT, DEFAULT_CPS_LIMIT

@app.post("/calls", response_model=CreateCallResponse, status_code=202)
async def create_call(
    payload: CreateCallRequest,
    key_hash: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    concurrent_limit, cps_limit = get_limits(db, key_hash)
    call_id = str(uuid.uuid4())
    now_ms = int(time.time() * 1000)
    result = await redis_client.eval(
        RESERVE_CALL_LUA, 2,
        active_key_for(key_hash), cps_key_for(key_hash),
        call_id, now_ms, 1000, cps_limit, concurrent_limit, 3600,
    )
    if result == 1:
        raise HTTPException(status_code=429, detail={"error": "Rate limit exceeded", "reason": "concurrent call limit"})
    if result == 2:
        raise HTTPException(status_code=429, detail={"error": "Rate limit exceeded", "reason": "calls per second limit"})

    call = CallRecord(
        call_id=call_id,
        api_key_hash=key_hash,
        caller=payload.from_number,
        callee=payload.to,
        state="QUEUED",
        metadata_json=payload.metadata,
    )
    try:
        db.add(call)
        db.commit()
    except Exception:
        db.rollback()
        await redis_client.srem(active_key_for(key_hash), call_id)
        raise HTTPException(status_code=500, detail="Could not create call")

    await redis_client.set(f"call:{call_id}", json.dumps({
        "call_id": call_id, "from": call.caller, "to": call.callee,
        "state": "QUEUED", "metadata": call.metadata_json, "recording_url": None,
    }), ex=86400)
    await redis_client.publish(f"call-events:{call_id}", json.dumps({
        "call_id": call_id, "state": "QUEUED", "timestamp": time.time()
    }))
    progress_call.delay(call_id, key_hash)
    return CreateCallResponse(
        call_id=call_id,
        state="QUEUED",
        websocket_url=f"/ws/calls/{call_id}",
    )

@app.get("/calls/{call_id}", response_model=CallResponse)
async def get_call(
    call_id: str,
    key_hash: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    call = db.get(CallRecord, call_id)
    if not call or call.api_key_hash != key_hash:
        raise HTTPException(status_code=404, detail="Call not found")
    return CallResponse(
        call_id=call.call_id, from_number=call.caller, to=call.callee,
        state=call.state, metadata=call.metadata_json, recording_url=call.recording_url,
    )

@app.websocket("/ws/calls/{call_id}")
async def call_updates(websocket: WebSocket, call_id: str):
    # Browsers commonly pass the key as a query parameter for WebSockets.
    key = websocket.query_params.get("api_key")
    if not key or not await _is_valid_key(key):
        await websocket.close(code=1008)
        return
    key_hash = hash_api_key(key)
    cached = await redis_client.get(f"call:{call_id}")
    if not cached:
        await websocket.close(code=1008)
        return
    data = json.loads(cached)
    db_call_key = data.get("api_key_hash")
    # The initial Redis payload intentionally omits credentials. Verify ownership in DB.
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        call = db.get(CallRecord, call_id)
        if not call or call.api_key_hash != key_hash:
            await websocket.close(code=1008)
            return
    finally:
        db.close()

    await websocket.accept()
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(f"call-events:{call_id}")
    try:
        await websocket.send_json({"call_id": call_id, "state": data["state"]})
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("data"):
                event = json.loads(message["data"])
                await websocket.send_json(event)
                if event.get("state") == "RECORDING_UPLOADED":
                    # Keep socket open for clients that want to observe post-call work.
                    continue
            else:
                await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await pubsub.unsubscribe(f"call-events:{call_id}")
        await pubsub.aclose()

async def _is_valid_key(key: str) -> bool:
    from app.config import API_KEYS
    import secrets
    return any(secrets.compare_digest(key, item) for item in API_KEYS)

@app.get("/metrics", response_model=MetricsResponse)
async def metrics(
    key_hash: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(CallRecord).where(CallRecord.api_key_hash == key_hash)) or 0
    active = await redis_client.scard(active_key_for(key_hash))
    cps = await redis_client.zcard(cps_key_for(key_hash))
    uploads = db.scalar(
        select(func.count()).select_from(CallRecord).where(
            CallRecord.api_key_hash == key_hash, CallRecord.recording_url.is_not(None)
        )
    ) or 0
    return MetricsResponse(total=total, active=active, cps=cps, uploads=uploads)

@app.get("/metrics/prometheus", response_class=PlainTextResponse)
async def prometheus_metrics(
    key_hash: str = Depends(require_api_key),
    db: Session = Depends(get_db),
):
    total = db.scalar(select(func.count()).select_from(CallRecord).where(CallRecord.api_key_hash == key_hash)) or 0
    active = await redis_client.scard(active_key_for(key_hash))
    uploads = db.scalar(select(func.count()).select_from(CallRecord).where(
        CallRecord.api_key_hash == key_hash, CallRecord.recording_url.is_not(None)
    )) or 0
    return f"calls_total {total}\\ncalls_active {active}\\nrecording_uploads_total {uploads}\\n"

@app.get("/recordings/{filename}")
async def get_recording(filename: str):
    # Mock-bucket access is deliberately read-only and limited to generated files.
    path = (Path(RECORDING_DIR) / filename).resolve()
    root = Path(RECORDING_DIR).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="Recording not found")
    from fastapi.responses import FileResponse
    return FileResponse(path, media_type="audio/mpeg", filename=filename)

@app.on_event("shutdown")
async def shutdown():
    await redis_client.aclose()
