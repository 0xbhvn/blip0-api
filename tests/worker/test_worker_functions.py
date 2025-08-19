"""Test cases for ARQ worker functions."""

import asyncio
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from arq.worker import Worker

# Prevent database initialization during import
with patch('src.app.core.db.database.async_engine'), \
     patch('src.app.core.db.database.local_session'):
    from src.app.core.worker.functions import sample_background_task, shutdown, startup


class TestSampleBackgroundTask:
    """Test cases for sample_background_task function."""

    @pytest.mark.asyncio
    async def test_sample_background_task_success(self):
        """Test successful execution of sample background task."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_name = "test_task"

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act
            result = await sample_background_task(mock_ctx, task_name)

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == f"Task {task_name} is complete!"
            assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_sample_background_task_empty_name(self):
        """Test sample background task with empty name."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_name = ""

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act
            result = await sample_background_task(mock_ctx, task_name)

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == "Task  is complete!"

    @pytest.mark.asyncio
    async def test_sample_background_task_with_special_characters(self):
        """Test sample background task with special characters in name."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_name = "test-task_123@domain.com"

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act
            result = await sample_background_task(mock_ctx, task_name)

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == f"Task {task_name} is complete!"

    @pytest.mark.asyncio
    async def test_sample_background_task_with_unicode(self):
        """Test sample background task with unicode characters."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_name = "测试任务_ñáéíóú"

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act
            result = await sample_background_task(mock_ctx, task_name)

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == f"Task {task_name} is complete!"

    @pytest.mark.asyncio
    async def test_sample_background_task_long_name(self):
        """Test sample background task with very long name."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_name = "a" * 1000  # Very long task name

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act
            result = await sample_background_task(mock_ctx, task_name)

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == f"Task {task_name} is complete!"
            assert len(result) == len(f"Task {task_name} is complete!")

    @pytest.mark.asyncio
    async def test_sample_background_task_cancellation(self):
        """Test cancellation of sample background task."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_name = "cancelled_task"

        # Create a task that will be cancelled
        async def cancelled_sleep(duration):
            await asyncio.sleep(duration)

        with patch('asyncio.sleep', side_effect=asyncio.CancelledError()):
            # Act & Assert
            with pytest.raises(asyncio.CancelledError):
                await sample_background_task(mock_ctx, task_name)

    @pytest.mark.asyncio
    async def test_sample_background_task_with_worker_attributes(self):
        """Test sample background task with worker context having attributes."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        mock_ctx.pool = Mock()
        mock_ctx.redis = Mock()
        mock_ctx.job_id = "test-job-123"
        task_name = "test_task"

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act
            result = await sample_background_task(mock_ctx, task_name)

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == f"Task {task_name} is complete!"
            # Verify worker context is accessible (though not used in this function)
            assert mock_ctx.job_id == "test-job-123"

    @pytest.mark.asyncio
    async def test_sample_background_task_timing(self):
        """Test that sample background task takes expected time."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_name = "timing_test"

        # Use real asyncio.sleep with short duration for timing test
        with patch('asyncio.sleep') as mock_sleep:
            # Make sleep actually await but with 0 duration
            future = asyncio.Future()
            future.set_result(None)
            mock_sleep.return_value = future

            # Act
            import time
            start_time = time.time()
            result = await sample_background_task(mock_ctx, task_name)
            end_time = time.time()

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == f"Task {task_name} is complete!"
            # Since we mocked sleep, execution should be very fast
            assert end_time - start_time < 0.1


class TestStartupFunction:
    """Test cases for worker startup function."""

    @pytest.mark.asyncio
    async def test_startup_success(self, caplog):
        """Test successful worker startup."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.INFO):
            result = await startup(mock_ctx)

        # Assert
        assert result is None
        assert "Worker Started" in caplog.text
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "INFO"
        assert caplog.records[0].message == "Worker Started"

    @pytest.mark.asyncio
    async def test_startup_with_worker_attributes(self, caplog):
        """Test startup with worker having various attributes."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        mock_ctx.pool = Mock()
        mock_ctx.redis = Mock()
        mock_ctx.functions = ["sample_background_task"]

        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.INFO):
            result = await startup(mock_ctx)

        # Assert
        assert result is None
        assert "Worker Started" in caplog.text
        # Verify worker context is accessible (though not used in this function)
        assert mock_ctx.functions == ["sample_background_task"]

    @pytest.mark.asyncio
    async def test_startup_logging_level(self, caplog):
        """Test that startup logs at INFO level."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.DEBUG):  # Capture DEBUG and above
            await startup(mock_ctx)

        # Assert
        info_records = [record for record in caplog.records if record.levelname == "INFO"]
        assert len(info_records) == 1
        assert info_records[0].message == "Worker Started"

    @pytest.mark.asyncio
    async def test_startup_multiple_calls(self, caplog):
        """Test multiple calls to startup function."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.INFO):
            await startup(mock_ctx)
            await startup(mock_ctx)
            await startup(mock_ctx)

        # Assert
        startup_records = [record for record in caplog.records if "Worker Started" in record.message]
        assert len(startup_records) == 3


class TestShutdownFunction:
    """Test cases for worker shutdown function."""

    @pytest.mark.asyncio
    async def test_shutdown_success(self, caplog):
        """Test successful worker shutdown."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.INFO):
            result = await shutdown(mock_ctx)

        # Assert
        assert result is None
        assert "Worker end" in caplog.text
        assert len(caplog.records) == 1
        assert caplog.records[0].levelname == "INFO"
        assert caplog.records[0].message == "Worker end"

    @pytest.mark.asyncio
    async def test_shutdown_with_worker_attributes(self, caplog):
        """Test shutdown with worker having various attributes."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        mock_ctx.pool = Mock()
        mock_ctx.redis = Mock()
        mock_ctx.functions = ["sample_background_task"]
        mock_ctx.jobs_complete = 42

        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.INFO):
            result = await shutdown(mock_ctx)

        # Assert
        assert result is None
        assert "Worker end" in caplog.text
        # Verify worker context is accessible (though not used in this function)
        assert mock_ctx.jobs_complete == 42

    @pytest.mark.asyncio
    async def test_shutdown_logging_level(self, caplog):
        """Test that shutdown logs at INFO level."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.DEBUG):  # Capture DEBUG and above
            await shutdown(mock_ctx)

        # Assert
        info_records = [record for record in caplog.records if record.levelname == "INFO"]
        assert len(info_records) == 1
        assert info_records[0].message == "Worker end"

    @pytest.mark.asyncio
    async def test_shutdown_multiple_calls(self, caplog):
        """Test multiple calls to shutdown function."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.INFO):
            await shutdown(mock_ctx)
            await shutdown(mock_ctx)
            await shutdown(mock_ctx)

        # Assert
        shutdown_records = [record for record in caplog.records if "Worker end" in record.message]
        assert len(shutdown_records) == 3


class TestWorkerFunctionErrorHandling:
    """Test error handling scenarios for worker functions."""

    @pytest.mark.asyncio
    async def test_sample_task_with_none_context(self):
        """Test sample background task with None context."""
        # Arrange
        task_name = "test_task"

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act
            result = await sample_background_task(None, task_name)

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == f"Task {task_name} is complete!"

    @pytest.mark.asyncio
    async def test_startup_with_none_context(self, caplog):
        """Test startup with None context."""
        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.INFO):
            result = await startup(None)

        # Assert
        assert result is None
        assert "Worker Started" in caplog.text

    @pytest.mark.asyncio
    async def test_shutdown_with_none_context(self, caplog):
        """Test shutdown with None context."""
        # Clear any existing log records
        caplog.clear()

        # Act
        with caplog.at_level(logging.INFO):
            result = await shutdown(None)

        # Assert
        assert result is None
        assert "Worker end" in caplog.text

    @pytest.mark.asyncio
    async def test_sample_task_with_none_name(self):
        """Test sample background task with None name."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act
            result = await sample_background_task(mock_ctx, None)

            # Assert
            mock_sleep.assert_called_once_with(5)
            assert result == "Task None is complete!"

    @pytest.mark.asyncio
    async def test_functions_preserve_async_context(self):
        """Test that all functions preserve async context properly."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_name = "context_test"

        # Create context variable to test preservation
        import contextvars
        test_var = contextvars.ContextVar('test_var', default=None)
        test_var.set('test_value')

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock):
            # Act - all functions should preserve context
            result = await sample_background_task(mock_ctx, task_name)
            await startup(mock_ctx)
            await shutdown(mock_ctx)

            # Assert - context should be preserved
            assert test_var.get() == 'test_value'
            assert result == f"Task {task_name} is complete!"


class TestWorkerFunctionTypes:
    """Test type annotations and function signatures."""

    def test_sample_background_task_signature(self):
        """Test sample_background_task function signature."""
        import inspect

        sig = inspect.signature(sample_background_task)
        params = sig.parameters

        # Check parameter names and types
        assert 'ctx' in params
        assert 'name' in params
        assert len(params) == 2

        # Check parameter annotations
        assert params['ctx'].annotation == Worker
        assert params['name'].annotation == str

        # Check return annotation
        assert sig.return_annotation == str

    def test_startup_function_signature(self):
        """Test startup function signature."""
        import inspect

        sig = inspect.signature(startup)
        params = sig.parameters

        # Check parameter names and types
        assert 'ctx' in params
        assert len(params) == 1

        # Check parameter annotations
        assert params['ctx'].annotation == Worker

        # Check return annotation
        assert sig.return_annotation is None

    def test_shutdown_function_signature(self):
        """Test shutdown function signature."""
        import inspect

        sig = inspect.signature(shutdown)
        params = sig.parameters

        # Check parameter names and types
        assert 'ctx' in params
        assert len(params) == 1

        # Check parameter annotations
        assert params['ctx'].annotation == Worker

        # Check return annotation
        assert sig.return_annotation is None

    def test_functions_are_async(self):
        """Test that all functions are properly async."""
        import inspect

        assert inspect.iscoroutinefunction(sample_background_task)
        assert inspect.iscoroutinefunction(startup)
        assert inspect.iscoroutinefunction(shutdown)


class TestWorkerFunctionPerformance:
    """Test performance characteristics of worker functions."""

    @pytest.mark.asyncio
    async def test_startup_performance(self):
        """Test startup function performance."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Act
        import time
        start_time = time.time()
        await startup(mock_ctx)
        end_time = time.time()

        # Assert - startup should be very fast since it just logs
        assert end_time - start_time < 0.1

    @pytest.mark.asyncio
    async def test_shutdown_performance(self):
        """Test shutdown function performance."""
        # Arrange
        mock_ctx = Mock(spec=Worker)

        # Act
        import time
        start_time = time.time()
        await shutdown(mock_ctx)
        end_time = time.time()

        # Assert - shutdown should be very fast since it just logs
        assert end_time - start_time < 0.1

    @pytest.mark.asyncio
    async def test_multiple_tasks_concurrency(self):
        """Test concurrent execution of multiple sample tasks."""
        # Arrange
        mock_ctx = Mock(spec=Worker)
        task_names = [f"task_{i}" for i in range(10)]

        # Mock asyncio.sleep to avoid actual delay
        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Act - run tasks concurrently
            tasks = [
                sample_background_task(mock_ctx, name)
                for name in task_names
            ]
            results = await asyncio.gather(*tasks)

            # Assert
            assert len(results) == 10
            for i, result in enumerate(results):
                assert result == f"Task task_{i} is complete!"

            # Sleep should be called once per task
            assert mock_sleep.call_count == 10
