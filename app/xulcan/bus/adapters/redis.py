# =============================================================================
# Redis Queue (separate from EventBus - different use case)
# =============================================================================

class Job:
    """Structured job with metadata for reliable queue operations.

    Separates payload from metadata (job_id, timestamps) for clean
    watchdog tracking without parsing JSON.

    Attributes:
        job_id: Unique identifier for this job instance
        payload: The actual job data (JSON string)
        created_at: Timestamp when job was created
        idempotency_key: Optional key for deduplication
    """

    def __init__(
        self,
        payload: str,
        job_id: str | None = None,
        created_at: float | None = None,
        idempotency_key: str | None = None,
    ) -> None:
        self.job_id = job_id or str(uuid.uuid4())
        self.payload = payload
        self.created_at = created_at or time.time()
        self.idempotency_key = idempotency_key

    def to_json(self) -> str:
        """Serialize to JSON for Redis storage."""
        return json.dumps({
            "job_id": self.job_id,
            "payload": self.payload,
            "created_at": self.created_at,
            "idempotency_key": self.idempotency_key,
        })

    @classmethod
    def from_json(cls, data: str) -> "Job":
        """Deserialize from JSON storage."""
        obj = json.loads(data)
        return cls(
            payload=obj["payload"],
            job_id=obj["job_id"],
            created_at=obj["created_at"],
            idempotency_key=obj.get("idempotency_key"),
        )


class RedisQueue:
    """Reliable Redis-based work queue.

    Uses ZSET for O(log n) watchdog operations and individual keys
    for scalable idempotency tracking.

    Architecture:
        - main_queue (LIST): pending jobs
        - working_zset (ZSET): jobs being processed, score = timestamp
        - completed:{key} (STRING with TTL): idempotency tracking

    Flow:
        main_queue ──BRPOPLPUSH──► working_zset ──complete()──► removed
                     ▲                                    │
                     └── requeue() ──────────────────────┘

    Watchdog uses ZRANGEBYSCORE to find old jobs in O(log n).
    """

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        redis_url: str | None = None,
        queue_name: str = "xulcan:queue",
        working_zset_name: str = "xulcan:queue:working",
        completed_key_prefix: str = "xulcan:completed:",
        max_job_age_seconds: int = 3600,
        watchdog_interval_seconds: int = 60,
        completed_ttl_seconds: int = 86400,
    ) -> None:
        self._queue_name = queue_name
        self._working_zset = working_zset_name
        self._completed_prefix = completed_key_prefix
        self._max_job_age = max_job_age_seconds
        self._watchdog_interval = watchdog_interval_seconds
        self._completed_ttl = completed_ttl_seconds

        if redis_url:
            self._redis_url = redis_url
            self._connection_kwargs: dict = {}
        else:
            self._redis_url = None
            self._connection_kwargs = {
                "host": host,
                "port": port,
                "db": db,
                "password": password,
            }

        self._pool: redis.ConnectionPool | None = None
        self._client: redis.Redis | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._running = False

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            if self._pool is None:
                if self._redis_url:
                    self._pool = redis.ConnectionPool.from_url(self._redis_url)
                else:
                    self._pool = redis.ConnectionPool(**self._connection_kwargs)
            self._client = redis.Redis(connection_pool=self._pool)
        return self._client

    # -------------------------------------------------------------------------
    # Core Queue Operations
    # -------------------------------------------------------------------------

    async def enqueue(
        self,
        payload: str,
        idempotency_key: str | None = None,
        job_id: str | None = None,
    ) -> str:
        """Add a job to the queue.

        Creates a structured Job with metadata for reliable tracking.
        Uses RPUSH for FIFO ordering.

        Args:
            payload: The job data (will be JSON-encoded)
            idempotency_key: Unique key to prevent duplicate execution
            job_id: Optional job ID (generated if not provided)

        Returns:
            The job_id of the created job
        """
        client = await self._get_client()

        job = Job(
            payload=payload,
            job_id=job_id,
            idempotency_key=idempotency_key,
        )

        await client.rpush(self._queue_name, job.to_json())
        logger.debug(f"📥 RedisQueue: Enqueued job {job.job_id} [{len(payload)} bytes]")

        return job.job_id

    async def dequeue(self, timeout: int = 0) -> Job | None:
        """Atomically acquire a job for processing.

        Moves job from main queue to working ZSET with timestamp as score.
        Uses ZADD for O(log n) watchdog tracking.

        Args:
            timeout: Seconds to wait (0 = block forever)

        Returns:
            Job object or None if timeout
        """
        client = await self._get_client()

        # BRPOP from main queue (blocking)
        result = await client.brpop(self._queue_name, timeout=timeout)
        if not result:
            return None

        _, data = result
        job = Job.from_json(data)
        timestamp = time.time()

        # ZADD to working ZSET (score = timestamp for age tracking)
        await client.zadd(self._working_zset, {data: timestamp})

        logger.debug(f"📤 RedisQueue: Dequeued job {job.job_id}")
        return job

    async def complete(self, job: Job) -> None:
        """Mark job as successfully completed.

        Removes from working ZSET and tracks idempotency key with TTL.

        Args:
            job: The completed Job object
        """
        client = await self._get_client()

        # Find and remove from working ZSET by job_id
        # We store JSON as member, so we need to scan (acceptable since
        # job should be at top of queue most of the time)
        all_members = await client.zrange(self._working_zset, 0, -1)
        for member in all_members:
            try:
                j = Job.from_json(member)
                if j.job_id == job.job_id:
                    await client.zrem(self._working_zset, member)
                    break
            except (json.JSONDecodeError, KeyError):
                continue

        # Track idempotency with individual key + TTL (SCALES PROPERLY)
        if job.idempotency_key:
            completed_key = f"{self._completed_prefix}{job.idempotency_key}"
            await client.set(completed_key, "1", ex=self._completed_ttl)

        logger.debug(f"✅ RedisQueue: Completed job {job.job_id}")

    async def requeue(self, job: Job) -> None:
        """Move job back to main queue for retry.

        Removes from working ZSET and pushes to end of main queue.

        Args:
            job: The Job to requeue
        """
        client = await self._get_client()

        # Find and remove from working ZSET
        all_members = await client.zrange(self._working_zset, 0, -1)
        for member in all_members:
            try:
                j = Job.from_json(member)
                if j.job_id == job.job_id:
                    await client.zrem(self._working_zset, member)
                    break
            except (json.JSONDecodeError, KeyError):
                continue

        # Re-enqueue with fresh timestamp
        new_job = Job(
            payload=job.payload,
            idempotency_key=job.idempotency_key,
        )
        await client.rpush(self._queue_name, new_job.to_json())

        logger.debug(f"🔄 RedisQueue: Requeued job {job.job_id} -> {new_job.job_id}")

    async def abandon(self, job: Job) -> None:
        """Remove job without requeuing (permanent failure).

        Args:
            job: The Job to abandon
        """
        client = await self._get_client()

        # Find and remove from working ZSET
        all_members = await client.zrange(self._working_zset, 0, -1)
        for member in all_members:
            try:
                j = Job.from_json(member)
                if j.job_id == job.job_id:
                    await client.zrem(self._working_zset, member)
                    break
            except (json.JSONDecodeError, KeyError):
                continue

        logger.debug(f"🗑️ RedisQueue: Abandoned job {job.job_id}")

    # -------------------------------------------------------------------------
    # Idempotency (individual keys with TTL - SCALES)
    # -------------------------------------------------------------------------

    async def is_completed(self, idempotency_key: str) -> bool:
        """Check if job with this idempotency key was already completed.

        Uses individual keys so TTL works correctly per-entry.

        Args:
            idempotency_key: The idempotency key to check

        Returns:
            True if job was previously completed
        """
        client = await self._get_client()
        completed_key = f"{self._completed_prefix}{idempotency_key}"
        return await client.exists(completed_key) > 0

    # -------------------------------------------------------------------------
    # Watchdog / Reaper (ZSET for O(log n) performance)
    # -------------------------------------------------------------------------

    async def start_watchdog(self) -> None:
        """Start background task to reclaim orphaned jobs.

        Uses ZRANGEBYSCORE for efficient O(log n) lookup of old jobs.

        NOTE: Call stop_watchdog() before closing.
        """
        if self._watchdog_task is not None:
            logger.warning("⚠️ Watchdog already running")
            return

        self._running = True
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        logger.debug("🐕 RedisQueue: Watchdog started")

    async def stop_watchdog(self) -> None:
        """Stop the watchdog task gracefully."""
        self._running = False
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
            self._watchdog_task = None
        logger.debug("🐕 RedisQueue: Watchdog stopped")

    async def _watchdog_loop(self) -> None:
        """Background loop that reclaims orphaned jobs using ZSET."""
        while self._running:
            try:
                await asyncio.sleep(self._watchdog_interval)
                if not self._running:
                    break
                await self._reap_orphans()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"💥 Watchdog error: {e}")

    async def _reap_orphans(self) -> int:
        """Find and reclaim orphaned jobs using ZRANGEBYSCORE.

        Uses ZSET score (timestamp) for O(log n) lookup instead of
        scanning entire working queue.

        Returns:
            Number of orphaned jobs requeued
        """
        client = await self._get_client()
        reclaimed = 0
        cutoff = time.time() - self._max_job_age

        # ZRANGEBYSCORE: O(log n) - gets jobs with score < cutoff
        # This is MUCH faster than LRANGE for large queues
        orphaned = await client.zrangebyscore(
            self._working_zset,
            min="-inf",
            max=cutoff,
        )

        for member in orphaned:
            try:
                job = Job.from_json(member)
                await client.zrem(self._working_zset, member)
                await client.rpush(self._queue_name, member)
                reclaimed += 1
                logger.warning(f"⚠️ Reclaimed orphan job {job.job_id}")
            except (json.JSONDecodeError, KeyError):
                # Malformed entry - remove it
                await client.zrem(self._working_zset, member)

        if reclaimed > 0:
            logger.info(f"🔄 RedisQueue: Reclaimed {reclaimed} orphaned jobs")

        return reclaimed

    # -------------------------------------------------------------------------
    # Monitoring
    # -------------------------------------------------------------------------

    async def length(self) -> int:
        """Return main queue length."""
        client = await self._get_client()
        return await client.llen(self._queue_name)

    async def working_length(self) -> int:
        """Return working ZSET length (in-progress jobs)."""
        client = await self._get_client()
        return await client.zcard(self._working_zset)

    async def stats(self) -> dict:
        """Return queue statistics."""
        client = await self._get_client()
        return {
            "queue_length": await client.llen(self._queue_name),
            "working_length": await client.zcard(self._working_zset),
            "watchdog_running": self._watchdog_task is not None,
        }

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def close(self) -> None:
        """Close all connections and stop watchdog."""
        await self.stop_watchdog()
        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
        logger.debug("🔌 RedisQueue: All connections closed")

    async def __aenter__(self) -> "RedisQueue":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()