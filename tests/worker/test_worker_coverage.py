"""Direct coverage tests for worker modules to ensure >80% coverage."""

import asyncio
import sys
from unittest.mock import AsyncMock, Mock, patch

# Mock database dependencies to avoid connection issues
mock_db = Mock()
mock_db.async_engine = Mock()
mock_db.local_session = Mock()
mock_config = Mock()
mock_config.settings = Mock()
mock_config.settings.REDIS_QUEUE_HOST = "localhost"
mock_config.settings.REDIS_QUEUE_PORT = 6379

sys.modules['src.app.core.db.database'] = mock_db
sys.modules['src.app.core.config'] = mock_config

# Now we can import the worker modules
from src.app.core.worker.functions import sample_background_task, shutdown, startup
from src.app.core.worker.settings import REDIS_QUEUE_HOST, REDIS_QUEUE_PORT, WorkerSettings


def test_worker_settings_coverage():
    """Test WorkerSettings to achieve full coverage of settings.py."""
    # Test all attributes exist
    assert hasattr(WorkerSettings, 'functions')
    assert hasattr(WorkerSettings, 'redis_settings')
    assert hasattr(WorkerSettings, 'on_startup')
    assert hasattr(WorkerSettings, 'on_shutdown')
    assert hasattr(WorkerSettings, 'handle_signals')

    # Test values
    assert isinstance(WorkerSettings.functions, list)
    assert len(WorkerSettings.functions) >= 1
    assert WorkerSettings.handle_signals is False
    assert callable(WorkerSettings.on_startup)
    assert callable(WorkerSettings.on_shutdown)

    # Test Redis constants
    assert isinstance(REDIS_QUEUE_HOST, str)
    assert isinstance(REDIS_QUEUE_PORT, int)
    assert REDIS_QUEUE_PORT > 0


async def test_worker_functions_coverage():
    """Test worker functions to achieve better coverage of functions.py."""
    from arq.worker import Worker

    mock_ctx = Mock(spec=Worker)

    # Test sample_background_task - this covers the main logic
    with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
        result = await sample_background_task(mock_ctx, "test_task")
        mock_sleep.assert_called_once_with(5)
        assert result == "Task test_task is complete!"

    # Test startup function - this should cover the logging line
    with patch('logging.info') as mock_log:
        await startup(mock_ctx)
        mock_log.assert_called_once_with("Worker Started")

    # Test shutdown function - this should cover the logging line
    with patch('logging.info') as mock_log:
        await shutdown(mock_ctx)
        mock_log.assert_called_once_with("Worker end")


def test_import_coverage():
    """Test imports to ensure all module-level code is covered."""
    # These imports should cover the module-level imports and setup
    import src.app.core.worker.functions as functions_module
    import src.app.core.worker.settings as settings_module

    # Test that all expected attributes are present
    assert hasattr(functions_module, 'sample_background_task')
    assert hasattr(functions_module, 'startup')
    assert hasattr(functions_module, 'shutdown')
    assert hasattr(functions_module, 'asyncio')
    assert hasattr(functions_module, 'logging')
    assert hasattr(functions_module, 'uvloop')

    assert hasattr(settings_module, 'WorkerSettings')
    assert hasattr(settings_module, 'REDIS_QUEUE_HOST')
    assert hasattr(settings_module, 'REDIS_QUEUE_PORT')


def test_function_signatures():
    """Test function signatures to ensure type checking code is covered."""
    import inspect

    from arq.worker import Worker

    # Test sample_background_task signature
    sig = inspect.signature(sample_background_task)
    params = sig.parameters
    assert 'ctx' in params
    assert 'name' in params
    assert params['ctx'].annotation == Worker
    assert params['name'].annotation == str
    assert sig.return_annotation == str

    # Test startup signature
    sig = inspect.signature(startup)
    params = sig.parameters
    assert 'ctx' in params
    assert params['ctx'].annotation == Worker

    # Test shutdown signature
    sig = inspect.signature(shutdown)
    params = sig.parameters
    assert 'ctx' in params
    assert params['ctx'].annotation == Worker


if __name__ == "__main__":
    # Run the async test
    asyncio.run(test_worker_functions_coverage())
    print("All worker coverage tests passed!")
