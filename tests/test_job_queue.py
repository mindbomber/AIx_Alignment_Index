from __future__ import annotations

from collections import defaultdict, deque

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from aix_platform.config import Settings
from aix_platform.database import Base
from aix_platform.job_queue import RedisJobQueue, recover_pending_jobs
from aix_platform.orm import Job, Organization, User


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def zrem(self, key, value):
        self.operations.append(("zrem", key, value))
        return self

    def lpush(self, key, value):
        self.operations.append(("lpush", key, value))
        return self

    def execute(self):
        for name, *args in self.operations:
            getattr(self.redis, name)(*args)


class FakeRedis:
    def __init__(self):
        self.lists = defaultdict(deque)
        self.sorted_sets = defaultdict(dict)

    def lpush(self, key, value):
        self.lists[key].appendleft(value)

    def brpop(self, key, timeout=0):
        if not self.lists[key]:
            return None
        return key, self.lists[key].pop()

    def zadd(self, key, values):
        self.sorted_sets[key].update(values)

    def zrangebyscore(self, key, minimum, maximum, start=0, num=100):
        values = [
            value
            for value, score in sorted(
                self.sorted_sets[key].items(), key=lambda item: item[1]
            )
            if minimum <= score <= maximum
        ]
        return values[start : start + num]

    def zrem(self, key, value):
        self.sorted_sets[key].pop(value, None)

    def pipeline(self):
        return FakePipeline(self)


def test_redis_job_queue_orders_and_promotes_retries():
    settings = Settings(
        token_pepper="test-token-pepper-value",
        redis_url="redis://unused",
    )
    redis = FakeRedis()
    queue = RedisJobQueue(settings, client=redis)
    queue.enqueue("job-1")
    queue.enqueue("job-2")
    assert queue.dequeue() == "job-1"
    assert queue.dequeue() == "job-2"
    queue.retry("job-3", -1)
    assert queue.promote_due() == 1
    assert queue.dequeue() == "job-3"


def test_recover_pending_jobs_enqueues_durable_records():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    settings = Settings(
        token_pepper="test-token-pepper-value",
        redis_url="redis://unused",
    )
    redis = FakeRedis()
    queue = RedisJobQueue(settings, client=redis)
    with Session(engine) as db:
        organization = Organization(name="Queue", slug="queue")
        user = User(
            email="queue@example.com",
            display_name="Queue",
            password_hash="unused",
        )
        db.add_all([organization, user])
        db.flush()
        pending = Job(
            organization_id=organization.id,
            kind="assessment_report",
            idempotency_key="pending-job",
            payload_json={},
            created_by=user.id,
        )
        succeeded = Job(
            organization_id=organization.id,
            kind="assessment_report",
            status="succeeded",
            idempotency_key="finished-job",
            payload_json={},
            created_by=user.id,
        )
        db.add_all([pending, succeeded])
        db.commit()
        assert recover_pending_jobs(db, queue) == 1
        assert queue.dequeue() == pending.id
        assert queue.dequeue() is None
    engine.dispose()
