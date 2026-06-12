from __future__ import annotations

from datetime import datetime, timezone

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .orm import Job


class RedisJobQueue:
    def __init__(self, settings: Settings, client: Redis | None = None):
        if not settings.redis_url and client is None:
            raise ValueError("Redis URL is required for distributed job queues")
        self.redis = client or Redis.from_url(
            settings.redis_url or "", decode_responses=True
        )
        self.ready_key = settings.job_queue_name
        self.retry_key = f"{settings.job_queue_name}:retry"

    def enqueue(self, job_id: str) -> None:
        self.redis.lpush(self.ready_key, job_id)

    def dequeue(self, timeout: int = 1) -> str | None:
        result = self.redis.brpop(self.ready_key, timeout=timeout)
        if result is None:
            return None
        value = result[1]
        return value.decode() if isinstance(value, bytes) else str(value)

    def retry(self, job_id: str, delay_seconds: int) -> None:
        due = datetime.now(timezone.utc).timestamp() + delay_seconds
        self.redis.zadd(self.retry_key, {job_id: due})

    def promote_due(self, limit: int = 100) -> int:
        now = datetime.now(timezone.utc).timestamp()
        due = self.redis.zrangebyscore(self.retry_key, 0, now, start=0, num=limit)
        if not due:
            return 0
        pipeline = self.redis.pipeline()
        for raw_job_id in due:
            job_id = raw_job_id.decode() if isinstance(raw_job_id, bytes) else raw_job_id
            pipeline.zrem(self.retry_key, job_id)
            pipeline.lpush(self.ready_key, job_id)
        pipeline.execute()
        return len(due)


def enqueue_job(settings: Settings, job_id: str) -> bool:
    if not settings.redis_url:
        return False
    try:
        RedisJobQueue(settings).enqueue(job_id)
        return True
    except RedisError:
        if settings.environment == "production":
            raise
        return False


def recover_pending_jobs(
    db: Session, queue: RedisJobQueue, *, limit: int = 1000
) -> int:
    job_ids = list(
        db.scalars(
            select(Job.id)
            .where(Job.status == "pending")
            .order_by(Job.created_at)
            .limit(limit)
        )
    )
    for job_id in job_ids:
        queue.enqueue(job_id)
    return len(job_ids)
