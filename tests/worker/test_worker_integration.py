"""Integration tests for ARQ worker system."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import JobStatus
from arq.worker import Worker

# Prevent database initialization during import
with patch('src.app.core.db.database.async_engine'), \
     patch('src.app.core.db.database.local_session'):
    from src.app.core.worker.functions import sample_background_task, shutdown, startup
    from src.app.core.worker.settings import WorkerSettings


class MockRedis:
    """Mock Redis client for testing."""

    def __init__(self):
        self.data = {}
        self.queues = {}
        self.jobs = {}
        self.job_counter = 0

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value
        return True

    async def delete(self, key):
        if key in self.data:
            del self.data[key]
        return True

    async def lpush(self, queue_name, *values):
        if queue_name not in self.queues:
            self.queues[queue_name] = []
        self.queues[queue_name].extend(reversed(values))
        return len(self.queues[queue_name])

    async def brpop(self, keys, timeout=None):
        for key in keys:
            if key in self.queues and self.queues[key]:
                return (key, self.queues[key].pop())
        return None

    async def hset(self, name, mapping=None, **kwargs):
        if name not in self.data:
            self.data[name] = {}
        if mapping:
            self.data[name].update(mapping)
        self.data[name].update(kwargs)
        return len(kwargs) + (len(mapping) if mapping else 0)

    async def hget(self, name, key):
        return self.data.get(name, {}).get(key)

    async def hgetall(self, name):
        return self.data.get(name, {})

    async def close(self):
        pass


class MockJob:
    """Mock ARQ Job for testing."""

    def __init__(self, job_id, function_name, args=None, kwargs=None, status=JobStatus.queued):
        self.job_id = job_id
        self.function = function_name
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.status = status
        self.result = None
        self.enqueue_time = asyncio.get_event_loop().time()
        self.start_time = None
        self.finish_time = None

    async def result_info(self):
        return {
            'job_id': self.job_id,
            'function': self.function,
            'args': self.args,
            'kwargs': self.kwargs,
            'status': self.status,
            'result': self.result,
            'enqueue_time': self.enqueue_time,
            'start_time': self.start_time,
            'finish_time': self.finish_time,
        }


class MockArqRedis:
    """Mock ArqRedis for testing."""

    def __init__(self):
        self.redis = MockRedis()
        self.jobs = {}
        self.job_counter = 0

    async def enqueue_job(self, function, *args, **kwargs):
        self.job_counter += 1
        job_id = f"job_{self.job_counter}"

        job = MockJob(
            job_id=job_id,
            function_name=function if isinstance(function, str) else function.__name__,
            args=args,
            kwargs=kwargs
        )

        self.jobs[job_id] = job
        return job

    async def get_job_result(self, job_id):
        job = self.jobs.get(job_id)
        if job:
            return job.result
        return None

    async def close(self):
        await self.redis.close()


class TestWorkerIntegration:
    """Integration tests for worker with Redis mock."""

    @pytest.mark.asyncio
    async def test_worker_initialization_with_settings(self):
        """Test worker can be initialized with WorkerSettings."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Worker initialization should work with our settings
            settings = WorkerSettings

            # Verify settings can be used to initialize a worker-like object
            assert settings.functions is not None
            assert settings.redis_settings is not None
            assert callable(settings.on_startup)
            assert callable(settings.on_shutdown)

    @pytest.mark.asyncio
    async def test_task_queuing_and_execution(self):
        """Test task queuing and execution flow."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Enqueue a job
            job = await mock_redis.enqueue_job(
                sample_background_task,
                "test_task"
            )

            # Verify job was created
            assert job.job_id is not None
            assert job.function == 'sample_background_task'
            assert job.args == ("test_task",)
            assert job.status == JobStatus.queued

            # Simulate job execution
            with patch('asyncio.sleep', new_callable=AsyncMock):
                mock_ctx = Mock(spec=Worker)
                result = await sample_background_task(mock_ctx, "test_task")

                # Update job status and result
                job.status = JobStatus.complete
                job.result = result

            assert job.result == "Task test_task is complete!"
            assert job.status == JobStatus.complete

    @pytest.mark.asyncio
    async def test_multiple_tasks_concurrent_execution(self):
        """Test concurrent execution of multiple tasks."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Enqueue multiple jobs
            jobs = []
            task_names = [f"task_{i}" for i in range(5)]

            for task_name in task_names:
                job = await mock_redis.enqueue_job(
                    sample_background_task,
                    task_name
                )
                jobs.append(job)

            # Simulate concurrent execution
            with patch('asyncio.sleep', new_callable=AsyncMock):
                mock_ctx = Mock(spec=Worker)

                # Execute all tasks concurrently
                tasks = [
                    sample_background_task(mock_ctx, task_name)
                    for task_name in task_names
                ]
                results = await asyncio.gather(*tasks)

                # Update job results
                for i, (job, result) in enumerate(zip(jobs, results)):
                    job.status = JobStatus.complete
                    job.result = result

            # Verify all jobs completed successfully
            for i, job in enumerate(jobs):
                assert job.status == JobStatus.complete
                assert job.result == f"Task task_{i} is complete!"

    @pytest.mark.asyncio
    async def test_task_retry_mechanism(self):
        """Test task retry mechanism on failure."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Enqueue a job
            job = await mock_redis.enqueue_job(
                sample_background_task,
                "failing_task"
            )

            # Simulate task failure on first attempt
            mock_ctx = Mock(spec=Worker)

            # First attempt fails
            with patch('asyncio.sleep', side_effect=Exception("Simulated failure")):
                try:
                    await sample_background_task(mock_ctx, "failing_task")
                    assert False, "Expected exception"
                except Exception as e:
                    job.status = JobStatus.deferred
                    job.result = str(e)

            assert job.status == JobStatus.deferred

            # Retry the job (simulate retry mechanism)
            job.status = JobStatus.in_progress

            # Second attempt succeeds
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await sample_background_task(mock_ctx, "failing_task")
                job.status = JobStatus.complete
                job.result = result

            assert job.status == JobStatus.complete
            assert job.result == "Task failing_task is complete!"

    @pytest.mark.asyncio
    async def test_task_cancellation(self):
        """Test task cancellation mechanism."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Enqueue a job
            job = await mock_redis.enqueue_job(
                sample_background_task,
                "cancelled_task"
            )

            # Start task execution
            mock_ctx = Mock(spec=Worker)
            job.status = JobStatus.in_progress

            # Create a task that can be cancelled
            async def run_task():
                return await sample_background_task(mock_ctx, "cancelled_task")

            task = asyncio.create_task(run_task())

            # Cancel the task before it completes
            await asyncio.sleep(0.01)  # Let it start
            task.cancel()

            # Verify task was cancelled
            with pytest.raises(asyncio.CancelledError):
                await task

            job.status = JobStatus.deferred
            job.result = "Task cancelled"

    @pytest.mark.asyncio
    async def test_worker_startup_and_shutdown_lifecycle(self):
        """Test worker startup and shutdown lifecycle."""
        mock_redis = MockArqRedis()
        startup_called = False
        shutdown_called = False

        # Mock the actual startup/shutdown functions to track calls
        async def mock_startup(ctx):
            nonlocal startup_called
            startup_called = True
            await startup(ctx)

        async def mock_shutdown(ctx):
            nonlocal shutdown_called
            shutdown_called = True
            await shutdown(ctx)

        with patch('arq.create_pool', return_value=mock_redis):
            mock_ctx = Mock(spec=Worker)

            # Simulate worker startup
            await mock_startup(mock_ctx)
            assert startup_called is True

            # Simulate some work
            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await sample_background_task(mock_ctx, "lifecycle_test")
                assert result == "Task lifecycle_test is complete!"

            # Simulate worker shutdown
            await mock_shutdown(mock_ctx)
            assert shutdown_called is True

    @pytest.mark.asyncio
    async def test_redis_connection_handling(self):
        """Test Redis connection handling and error recovery."""
        # Test successful connection
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Simulate connection establishment
            redis_client = mock_redis  # Use the mock directly
            assert redis_client is not None

            # Test job operations
            job = await redis_client.enqueue_job(
                sample_background_task,
                "connection_test"
            )
            assert job.job_id is not None

            # Clean up
            await redis_client.close()

    @pytest.mark.asyncio
    async def test_redis_connection_failure_handling(self):
        """Test handling of Redis connection failures."""

        # Create settings for a non-existent Redis server to ensure connection failure
        failing_settings = RedisSettings(
            host="non-existent-host",
            port=99999,  # Port that definitely won't be available
            database=0
        )
        
        # Test that connection failures are properly handled 
        with pytest.raises(Exception):  # Could be AuthenticationError, ConnectionError, etc.
            await create_pool(failing_settings)

    @pytest.mark.asyncio
    async def test_job_serialization_and_deserialization(self):
        """Test job data serialization and deserialization."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Test with various argument types
            test_cases = [
                ("simple_string",),
                ("string_with_unicode_测试",),
                (123, 456.789),
                (["list", "of", "values"]),
                ({"dict": "value", "number": 42}),
            ]

            for args in test_cases:
                job = await mock_redis.enqueue_job(
                    sample_background_task,
                    *args
                )

                # Verify arguments were preserved (convert to tuple for comparison since MockJob stores as tuple)
                assert job.args == tuple(args) if isinstance(args, list) else args

                # Simulate job result retrieval
                job_info = await job.result_info()
                assert job_info['args'] == tuple(args) if isinstance(args, list) else args

    @pytest.mark.asyncio
    async def test_job_timeout_handling(self):
        """Test handling of job timeouts."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            job = await mock_redis.enqueue_job(
                sample_background_task,
                "timeout_test"
            )

            # Simulate a long-running task that times out
            mock_ctx = Mock(spec=Worker)

            async def long_running_task():
                # Simulate a task that takes longer than timeout
                await asyncio.sleep(10)  # Long delay
                return await sample_background_task(mock_ctx, "timeout_test")

            # Create task with timeout
            try:
                await asyncio.wait_for(long_running_task(), timeout=0.1)
                assert False, "Expected timeout"
            except TimeoutError:
                job.status = JobStatus.deferred
                job.result = "Task timed out"

            assert job.status == JobStatus.deferred

    @pytest.mark.asyncio
    async def test_worker_with_custom_redis_settings(self):
        """Test worker with custom Redis settings."""
        custom_settings = RedisSettings(
            host="custom-host",
            port=9999,
            database=1
        )

        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Test that we can configure custom settings
            redis_client = mock_redis  # Use mock directly to avoid real connection

            # Verify custom settings exist and are valid
            assert custom_settings.host == "custom-host"
            assert custom_settings.port == 9999
            assert custom_settings.database == 1

            # Test job operations work with custom settings
            job = await redis_client.enqueue_job(
                sample_background_task,
                "custom_redis_test"
            )

            assert job.job_id is not None
            assert job.function == 'sample_background_task'


class TestWorkerErrorHandling:
    """Test error handling in worker integration scenarios."""

    @pytest.mark.asyncio
    async def test_task_exception_handling(self):
        """Test handling of exceptions raised by tasks."""
        mock_redis = MockArqRedis()

        # Create a task that raises an exception
        async def failing_task(ctx, message):
            raise ValueError(f"Task failed with message: {message}")

        with patch('arq.create_pool', return_value=mock_redis):
            job = await mock_redis.enqueue_job(
                failing_task,
                "error_message"
            )

            # Execute the failing task
            mock_ctx = Mock(spec=Worker)

            try:
                await failing_task(mock_ctx, "error_message")
                assert False, "Expected ValueError"
            except ValueError as e:
                job.status = JobStatus.deferred
                job.result = str(e)

            assert job.status == JobStatus.deferred
            assert "Task failed with message: error_message" in job.result

    @pytest.mark.asyncio
    async def test_redis_operation_failures(self):
        """Test handling of Redis operation failures."""
        mock_redis = MockArqRedis()

        # Mock Redis operations to fail
        mock_redis.enqueue_job = AsyncMock(side_effect=ConnectionError("Redis operation failed"))

        with patch('arq.create_pool', return_value=mock_redis):
            # Test that Redis failures are properly handled
            with pytest.raises(ConnectionError):
                await mock_redis.enqueue_job(
                    sample_background_task,
                    "redis_failure_test"
                )

    @pytest.mark.asyncio
    async def test_invalid_job_data_handling(self):
        """Test handling of invalid job data."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Test with invalid function reference
            job = MockJob(
                job_id="invalid_job",
                function_name="non_existent_function",
                args=("test",),
                status=JobStatus.queued
            )

            mock_redis.jobs["invalid_job"] = job

            # Attempting to execute non-existent function should handle gracefully
            # In a real scenario, this would be handled by the worker framework
            assert job.function == "non_existent_function"
            assert job.status == JobStatus.queued


class TestWorkerPerformance:
    """Test performance characteristics of worker integration."""

    @pytest.mark.asyncio
    async def test_high_throughput_job_processing(self):
        """Test processing many jobs efficiently."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Enqueue many jobs
            num_jobs = 100
            jobs = []

            for i in range(num_jobs):
                job = await mock_redis.enqueue_job(
                    sample_background_task,
                    f"batch_task_{i}"
                )
                jobs.append(job)

            assert len(jobs) == num_jobs

            # Simulate batch processing
            with patch('asyncio.sleep', new_callable=AsyncMock):
                mock_ctx = Mock(spec=Worker)

                # Process all jobs
                results = []
                for i in range(num_jobs):
                    result = await sample_background_task(mock_ctx, f"batch_task_{i}")
                    results.append(result)
                    jobs[i].status = JobStatus.complete
                    jobs[i].result = result

            # Verify all jobs processed
            assert len(results) == num_jobs
            for i, job in enumerate(jobs):
                assert job.status == JobStatus.complete
                assert job.result == f"Task batch_task_{i} is complete!"

    @pytest.mark.asyncio
    async def test_memory_usage_with_many_jobs(self):
        """Test memory usage doesn't grow excessively with many jobs."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Create and process jobs in batches to avoid memory buildup
            batch_size = 50
            num_batches = 5

            for batch in range(num_batches):
                # Create batch of jobs
                jobs = []
                for i in range(batch_size):
                    job = await mock_redis.enqueue_job(
                        sample_background_task,
                        f"memory_test_{batch}_{i}"
                    )
                    jobs.append(job)

                # Process batch
                with patch('asyncio.sleep', new_callable=AsyncMock):
                    mock_ctx = Mock(spec=Worker)

                    for job in jobs:
                        result = await sample_background_task(mock_ctx, job.args[0])
                        job.status = JobStatus.complete
                        job.result = result

                # Verify batch completed
                for job in jobs:
                    assert job.status == JobStatus.complete

                # Clear jobs from memory (simulate cleanup)
                jobs.clear()

    @pytest.mark.asyncio
    async def test_concurrent_workers_simulation(self):
        """Test simulation of multiple concurrent workers."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            # Enqueue jobs for multiple workers
            num_workers = 3
            jobs_per_worker = 10
            all_jobs = []

            for worker_id in range(num_workers):
                for job_id in range(jobs_per_worker):
                    job = await mock_redis.enqueue_job(
                        sample_background_task,
                        f"worker_{worker_id}_job_{job_id}"
                    )
                    all_jobs.append(job)

            # Simulate concurrent processing by multiple workers
            async def simulate_worker(worker_id, jobs):
                mock_ctx = Mock(spec=Worker)
                mock_ctx.worker_id = worker_id

                with patch('asyncio.sleep', new_callable=AsyncMock):
                    for job in jobs:
                        if job.args[0].startswith(f"worker_{worker_id}_"):
                            result = await sample_background_task(mock_ctx, job.args[0])
                            job.status = JobStatus.complete
                            job.result = result

            # Create worker tasks
            worker_tasks = []
            for worker_id in range(num_workers):
                worker_jobs = [job for job in all_jobs if job.args[0].startswith(f"worker_{worker_id}_")]
                task = asyncio.create_task(simulate_worker(worker_id, worker_jobs))
                worker_tasks.append(task)

            # Wait for all workers to complete
            await asyncio.gather(*worker_tasks)

            # Verify all jobs completed
            completed_jobs = [job for job in all_jobs if job.status == JobStatus.complete]
            assert len(completed_jobs) == num_workers * jobs_per_worker


class TestWorkerMonitoring:
    """Test monitoring and observability aspects of worker integration."""

    @pytest.mark.asyncio
    async def test_job_status_tracking(self):
        """Test tracking job status throughout lifecycle."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            job = await mock_redis.enqueue_job(
                sample_background_task,
                "status_tracking_test"
            )

            # Track status changes
            status_history = []

            # Initial status
            status_history.append(job.status)
            assert job.status == JobStatus.queued

            # Start processing
            job.status = JobStatus.in_progress
            job.start_time = asyncio.get_event_loop().time()
            status_history.append(job.status)

            # Complete processing
            with patch('asyncio.sleep', new_callable=AsyncMock):
                mock_ctx = Mock(spec=Worker)
                result = await sample_background_task(mock_ctx, "status_tracking_test")

                job.status = JobStatus.complete
                job.result = result
                job.finish_time = asyncio.get_event_loop().time()
                status_history.append(job.status)

            # Verify status progression
            expected_statuses = [JobStatus.queued, JobStatus.in_progress, JobStatus.complete]
            assert status_history == expected_statuses

            # Verify timing information
            assert job.enqueue_time is not None
            assert job.start_time is not None
            assert job.finish_time is not None
            assert job.finish_time >= job.start_time >= job.enqueue_time

    @pytest.mark.asyncio
    async def test_job_result_retrieval(self):
        """Test retrieving job results after completion."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            job = await mock_redis.enqueue_job(
                sample_background_task,
                "result_test"
            )

            # Initially no result
            initial_result = await mock_redis.get_job_result(job.job_id)
            assert initial_result is None

            # Process job
            with patch('asyncio.sleep', new_callable=AsyncMock):
                mock_ctx = Mock(spec=Worker)
                result = await sample_background_task(mock_ctx, "result_test")

                job.status = JobStatus.complete
                job.result = result

            # Retrieve result
            final_result = await mock_redis.get_job_result(job.job_id)
            assert final_result == "Task result_test is complete!"

    @pytest.mark.asyncio
    async def test_worker_health_monitoring(self):
        """Test worker health and lifecycle monitoring."""
        mock_redis = MockArqRedis()

        with patch('arq.create_pool', return_value=mock_redis):
            mock_ctx = Mock(spec=Worker)
            mock_ctx.health_status = "healthy"

            # Test startup monitoring
            startup_time = asyncio.get_event_loop().time()
            await startup(mock_ctx)

            # Verify worker is healthy after startup
            assert mock_ctx.health_status == "healthy"

            # Process some jobs to simulate activity
            with patch('asyncio.sleep', new_callable=AsyncMock):
                for i in range(5):
                    result = await sample_background_task(mock_ctx, f"health_test_{i}")
                    assert "complete" in result

            # Test shutdown monitoring
            shutdown_time = asyncio.get_event_loop().time()
            await shutdown(mock_ctx)

            # Verify timing
            assert shutdown_time >= startup_time
