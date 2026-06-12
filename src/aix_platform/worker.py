from __future__ import annotations

import time

from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from aix.reporting import render_report
from aix.scoring import AIxResult

from .audit import append_audit_event
from .config import get_settings
from .database import SessionLocal
from .job_queue import RedisJobQueue, recover_pending_jobs
from .orm import Assessment, Job
from .privacy import process_next_privacy_request, purge_expired_evidence
from .webhooks import deliver_next_webhook


def process_job(db: Session, job_id: str | None = None) -> Job | None:
    query = select(Job).where(Job.status == "pending")
    if job_id is not None:
        query = query.where(Job.id == job_id)
    job = db.scalar(
        query.order_by(Job.created_at).with_for_update(skip_locked=True).limit(1)
    )
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    db.commit()

    try:
        if job.kind != "assessment_report":
            raise ValueError(f"Unsupported job kind: {job.kind}")
        assessment = db.scalar(
            select(Assessment).where(
                Assessment.id == job.payload_json["assessment_id"],
                Assessment.organization_id == job.organization_id,
            )
        )
        if assessment is None or assessment.result_json is None:
            raise ValueError("Finalized assessment result not found")
        output_format = job.payload_json.get("format", "markdown")
        content = render_report(AIxResult(**assessment.result_json), output_format)
        job.result_json = {
            "format": output_format,
            "content": content,
            "assessment_id": assessment.id,
            "result_sha256": assessment.result_sha256,
        }
        job.status = "succeeded"
        job.error = None
        append_audit_event(
            db,
            organization_id=job.organization_id,
            actor_user_id=job.created_by,
            action="job.succeed",
            entity_type="job",
            entity_id=job.id,
            payload={"kind": job.kind},
        )
    except Exception as exc:
        job.error = str(exc)
        job.status = "pending" if job.attempts < job.max_attempts else "failed"
        append_audit_event(
            db,
            organization_id=job.organization_id,
            actor_user_id=job.created_by,
            action="job.retry" if job.status == "pending" else "job.fail",
            entity_type="job",
            entity_id=job.id,
            payload={"kind": job.kind, "attempt": job.attempts, "error": job.error},
        )
    db.commit()
    return job


def process_next_job(db: Session) -> Job | None:
    return process_job(db)


def run() -> None:
    settings = get_settings()
    last_retention_run = 0.0
    last_recovery_run = 0.0
    queue = RedisJobQueue(settings) if settings.redis_url else None
    while True:
        job_id = None
        if queue:
            try:
                queue.promote_due()
                job_id = queue.dequeue(timeout=1)
            except RedisError:
                if settings.environment == "production":
                    time.sleep(1)
                    continue
        with SessionLocal() as db:
            job = process_job(db, job_id) if job_id else (
                process_next_job(db) if queue is None else None
            )
            if job and job.status == "pending" and queue:
                delay = settings.job_retry_base_seconds * (2 ** max(0, job.attempts - 1))
                queue.retry(job.id, delay)
            webhook = deliver_next_webhook(db, settings) if job is None else None
            privacy = (
                process_next_privacy_request(db, settings)
                if job is None and webhook is None
                else None
            )
            now = time.monotonic()
            if queue and now - last_recovery_run >= 30:
                try:
                    recover_pending_jobs(db, queue)
                    last_recovery_run = now
                except RedisError:
                    pass
            if now - last_retention_run >= 300:
                purge_expired_evidence(db, settings)
                last_retention_run = now
        if queue is None and job is None and webhook is None and privacy is None:
            time.sleep(1)
