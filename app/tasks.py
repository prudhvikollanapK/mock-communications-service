import os
import random
import time
from pathlib import Path
from celery import Celery
from sqlalchemy.orm import Session
from app.config import DATABASE_URL, REDIS_URL, RECORDING_DIR, CALL_MIN_DELAY, CALL_MAX_DELAY
from app.database import SessionLocal
from app.models import CallRecord
import redis

celery_app = Celery(
    "communications",
    broker=REDIS_URL,
    backend=REDIS_URL,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)

_sync_redis = redis.Redis.from_url(REDIS_URL, decode_responses=True)

def publish_state(call_id: str, state: str) -> None:
    _sync_redis.publish(f"call-events:{call_id}", __import__("json").dumps({
        "call_id": call_id, "state": state, "timestamp": time.time()
    }))

def update_state(db: Session, call: CallRecord, state: str) -> None:
    call.state = state
    db.commit()
    _sync_redis.set(f"call:{call.call_id}", __import__("json").dumps({
        "call_id": call.call_id,
        "from": call.caller,
        "to": call.callee,
        "state": state,
        "metadata": call.metadata_json,
        "recording_url": call.recording_url,
    }))
    publish_state(call.call_id, state)

@celery_app.task(name="app.tasks.progress_call", bind=True, max_retries=3)
def progress_call(self, call_id: str, key_hash: str) -> None:
    db = SessionLocal()
    try:
        call = db.get(CallRecord, call_id)
        if not call:
            return
        update_state(db, call, "RINGING")
        time.sleep(random.uniform(CALL_MIN_DELAY, CALL_MAX_DELAY))

        if random.random() < 0.75:
            update_state(db, call, "ANSWERED")
        else:
            update_state(db, call, "UNANSWERED")
        time.sleep(random.uniform(CALL_MIN_DELAY, CALL_MAX_DELAY))
        update_state(db, call, "COMPLETED")
        # Release the per-key concurrency slot as soon as the call completes.
        from app.redis_client import active_key_for
        _sync_redis.srem(active_key_for(key_hash), call_id)

        # A static mock recording is copied into a local mock bucket asynchronously.
        Path(RECORDING_DIR).mkdir(parents=True, exist_ok=True)
        recording_path = Path(RECORDING_DIR) / "mock_recording.mp3"
        if not recording_path.exists():
            recording_path.write_bytes(b"MOCK MP3 RECORDING - replace with a real sample file.\\n")
        call.recording_url = f"/recordings/{call.call_id}.mp3"
        target = Path(RECORDING_DIR) / f"{call.call_id}.mp3"
        target.write_bytes(recording_path.read_bytes())
        db.commit()
        _sync_redis.set(f"call:{call.call_id}", __import__("json").dumps({
            "call_id": call.call_id, "from": call.caller, "to": call.callee,
            "state": call.state, "metadata": call.metadata_json,
            "recording_url": call.recording_url,
        }))
        publish_state(call.call_id, "RECORDING_UPLOADED")
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=2)
    finally:
        db.close()
