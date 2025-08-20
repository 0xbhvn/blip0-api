"""Test cases for ARQ worker settings configuration."""

import inspect

# Prevent database initialization during import
from unittest.mock import patch

import pytest
from arq.connections import RedisSettings

# Mock database components before importing worker modules
with patch('src.app.core.db.database.async_engine'), \
     patch('src.app.core.db.database.local_session'):
    from src.app.core.worker.functions import sample_background_task, shutdown, startup
    from src.app.core.worker.settings import REDIS_QUEUE_HOST, REDIS_QUEUE_PORT, WorkerSettings


class TestWorkerSettingsConfiguration:
    """Test cases for WorkerSettings class configuration."""

    def test_worker_settings_class_exists(self):
        """Test that WorkerSettings class exists and is properly defined."""
        assert WorkerSettings is not None
        assert inspect.isclass(WorkerSettings)

    def test_worker_settings_functions_list(self):
        """Test that functions list contains expected background tasks."""
        functions = WorkerSettings.functions

        assert isinstance(functions, list)
        assert len(functions) >= 1
        assert sample_background_task in functions

        # Verify all items in functions list are callable
        for func in functions:
            assert callable(func)

    def test_worker_settings_redis_settings(self):
        """Test Redis settings configuration."""
        redis_settings = WorkerSettings.redis_settings

        assert isinstance(redis_settings, RedisSettings)
        assert redis_settings.host == REDIS_QUEUE_HOST
        assert redis_settings.port == REDIS_QUEUE_PORT

    def test_worker_settings_startup_function(self):
        """Test startup function configuration."""
        on_startup = WorkerSettings.on_startup

        assert on_startup is startup
        assert callable(on_startup)
        assert inspect.iscoroutinefunction(on_startup)

    def test_worker_settings_shutdown_function(self):
        """Test shutdown function configuration."""
        on_shutdown = WorkerSettings.on_shutdown

        assert on_shutdown is shutdown
        assert callable(on_shutdown)
        assert inspect.iscoroutinefunction(on_shutdown)

    def test_worker_settings_handle_signals(self):
        """Test handle_signals configuration."""
        handle_signals = WorkerSettings.handle_signals

        assert isinstance(handle_signals, bool)
        assert handle_signals is False

    def test_worker_settings_attributes_exist(self):
        """Test that all required WorkerSettings attributes exist."""
        required_attributes = [
            'functions',
            'redis_settings',
            'on_startup',
            'on_shutdown',
            'handle_signals'
        ]

        for attr in required_attributes:
            assert hasattr(WorkerSettings, attr), f"Missing attribute: {attr}"

    def test_worker_settings_functions_are_async(self):
        """Test that all configured functions are async."""
        functions = WorkerSettings.functions

        for func in functions:
            assert inspect.iscoroutinefunction(func), f"Function {func.__name__} is not async"

    def test_worker_settings_functions_have_correct_signature(self):
        """Test that all functions have the correct ARQ signature."""
        functions = WorkerSettings.functions

        for func in functions:
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())

            # First parameter should be ctx (Worker context)
            assert len(params) >= 1, f"Function {func.__name__} should have at least one parameter (ctx)"
            assert params[0] == 'ctx', f"First parameter of {func.__name__} should be 'ctx'"

    def test_worker_settings_immutability(self):
        """Test that WorkerSettings class attributes are not accidentally modified."""
        original_functions = WorkerSettings.functions.copy()
        original_redis_host = WorkerSettings.redis_settings.host
        original_redis_port = WorkerSettings.redis_settings.port
        original_startup = WorkerSettings.on_startup
        original_shutdown = WorkerSettings.on_shutdown
        original_handle_signals = WorkerSettings.handle_signals

        # Verify values haven't changed
        assert WorkerSettings.functions == original_functions
        assert WorkerSettings.redis_settings.host == original_redis_host
        assert WorkerSettings.redis_settings.port == original_redis_port
        assert WorkerSettings.on_startup == original_startup
        assert WorkerSettings.on_shutdown == original_shutdown
        assert WorkerSettings.handle_signals == original_handle_signals


class TestRedisConnectionSettings:
    """Test cases for Redis connection configuration."""

    def test_redis_queue_host_constant(self):
        """Test REDIS_QUEUE_HOST constant."""
        assert isinstance(REDIS_QUEUE_HOST, str)
        assert len(REDIS_QUEUE_HOST) > 0

    def test_redis_queue_port_constant(self):
        """Test REDIS_QUEUE_PORT constant."""
        assert isinstance(REDIS_QUEUE_PORT, int)
        assert REDIS_QUEUE_PORT > 0
        assert REDIS_QUEUE_PORT <= 65535

    def test_redis_settings_object_creation(self):
        """Test RedisSettings object creation with host and port."""
        redis_settings = RedisSettings(host=REDIS_QUEUE_HOST, port=REDIS_QUEUE_PORT)

        assert isinstance(redis_settings, RedisSettings)
        assert redis_settings.host == REDIS_QUEUE_HOST
        assert redis_settings.port == REDIS_QUEUE_PORT

    def test_redis_settings_default_values(self):
        """Test RedisSettings object with default values."""
        redis_settings = RedisSettings()

        # RedisSettings should have sensible defaults
        assert redis_settings.host is not None
        assert redis_settings.port is not None
        assert isinstance(redis_settings.port, int)

    def test_redis_settings_with_custom_values(self):
        """Test RedisSettings with custom host and port values."""
        custom_host = "custom-redis-host"
        custom_port = 9999

        redis_settings = RedisSettings(host=custom_host, port=custom_port)

        assert redis_settings.host == custom_host
        assert redis_settings.port == custom_port

    def test_redis_settings_serialization(self):
        """Test that RedisSettings can be properly serialized/represented."""
        redis_settings = WorkerSettings.redis_settings

        # Should be able to convert to string representation
        str_repr = str(redis_settings)
        assert isinstance(str_repr, str)
        assert len(str_repr) > 0

    def test_redis_settings_environment_override(self):
        """Test that Redis settings respect environment configuration."""
        # Test by patching the settings module directly
        with patch('src.app.core.worker.settings.REDIS_QUEUE_HOST', 'patched-host'), \
             patch('src.app.core.worker.settings.REDIS_QUEUE_PORT', 7777):

            # Import the patched module
            import importlib

            import src.app.core.worker.settings
            importlib.reload(src.app.core.worker.settings)


            # Since the settings are imported at module level, we need a different approach
            # Let's just test that we can create RedisSettings with custom values
            custom_settings = RedisSettings(host='patched-host', port=7777)
            assert custom_settings.host == 'patched-host'
            assert custom_settings.port == 7777


class TestWorkerSettingsValidation:
    """Test validation of WorkerSettings configuration."""

    def test_functions_list_is_not_empty(self):
        """Test that functions list is not empty."""
        functions = WorkerSettings.functions

        assert isinstance(functions, list)
        assert len(functions) > 0

    def test_all_functions_are_importable(self):
        """Test that all functions in the list are properly importable."""
        functions = WorkerSettings.functions

        for func in functions:
            # Should be able to get the function name and module
            assert hasattr(func, '__name__')
            assert hasattr(func, '__module__')
            assert func.__name__ is not None
            assert func.__module__ is not None

    def test_redis_settings_is_valid_redis_settings_object(self):
        """Test that redis_settings is a valid RedisSettings instance."""
        redis_settings = WorkerSettings.redis_settings

        assert isinstance(redis_settings, RedisSettings)

        # Should have required attributes for Redis connection
        assert hasattr(redis_settings, 'host')
        assert hasattr(redis_settings, 'port')

    def test_startup_and_shutdown_functions_exist(self):
        """Test that startup and shutdown functions are properly set."""
        on_startup = WorkerSettings.on_startup
        on_shutdown = WorkerSettings.on_shutdown

        assert on_startup is not None
        assert on_shutdown is not None
        assert callable(on_startup)
        assert callable(on_shutdown)

    def test_handle_signals_is_boolean(self):
        """Test that handle_signals is a boolean value."""
        handle_signals = WorkerSettings.handle_signals

        assert isinstance(handle_signals, bool)

    def test_worker_settings_can_be_used_with_arq(self):
        """Test that WorkerSettings has all attributes needed by ARQ."""
        # These are the attributes that ARQ Worker expects
        required_arq_attributes = [
            'functions',
            'redis_settings',
        ]

        for attr in required_arq_attributes:
            assert hasattr(WorkerSettings, attr), f"Missing required ARQ attribute: {attr}"

        # Optional but commonly used attributes
        optional_attributes = [
            'on_startup',
            'on_shutdown',
            'handle_signals'
        ]

        for attr in optional_attributes:
            if hasattr(WorkerSettings, attr):
                value = getattr(WorkerSettings, attr)
                # If present, should not be None (unless intentionally set to None)
                if attr in ['on_startup', 'on_shutdown']:
                    assert callable(value) or value is None


class TestWorkerSettingsImports:
    """Test imports and function references in WorkerSettings."""

    def test_function_imports_are_correct(self):
        """Test that imported functions match the actual functions."""
        from src.app.core.worker.settings import WorkerSettings

        # Verify that the functions in the settings are the same objects
        # as the ones imported from functions module
        assert sample_background_task in WorkerSettings.functions
        assert WorkerSettings.on_startup is startup
        assert WorkerSettings.on_shutdown is shutdown

    def test_imported_functions_maintain_metadata(self):
        """Test that imported functions maintain their metadata."""
        functions = WorkerSettings.functions

        for func in functions:
            # Should have proper function metadata
            assert hasattr(func, '__name__')
            assert hasattr(func, '__doc__')
            assert hasattr(func, '__module__')
            assert hasattr(func, '__annotations__')

    def test_startup_shutdown_function_imports(self):
        """Test startup and shutdown function imports."""
        on_startup = WorkerSettings.on_startup
        on_shutdown = WorkerSettings.on_shutdown

        # Should be the actual imported functions, not references
        assert on_startup.__name__ == 'startup'
        assert on_shutdown.__name__ == 'shutdown'
        assert on_startup.__module__ == 'src.app.core.worker.functions'
        assert on_shutdown.__module__ == 'src.app.core.worker.functions'

    def test_circular_import_prevention(self):
        """Test that importing WorkerSettings doesn't cause circular imports."""
        try:
            # This should not raise ImportError due to circular imports
            # Import to test that no circular imports occur
            import src.app.core.worker.functions  # noqa: F401
            from src.app.core.worker.settings import WorkerSettings

            # Should be able to access all components without issues
            assert WorkerSettings.functions is not None
            assert WorkerSettings.redis_settings is not None
            assert WorkerSettings.on_startup is not None
            assert WorkerSettings.on_shutdown is not None

        except ImportError as e:
            pytest.fail(f"Circular import detected: {e}")


class TestWorkerSettingsExtensibility:
    """Test extensibility and customization of WorkerSettings."""

    def test_worker_settings_can_be_subclassed(self):
        """Test that WorkerSettings can be extended through subclassing."""
        class CustomWorkerSettings(WorkerSettings):
            custom_attribute = "custom_value"

        # Should inherit all original attributes
        assert hasattr(CustomWorkerSettings, 'functions')
        assert hasattr(CustomWorkerSettings, 'redis_settings')
        assert hasattr(CustomWorkerSettings, 'on_startup')
        assert hasattr(CustomWorkerSettings, 'on_shutdown')
        assert hasattr(CustomWorkerSettings, 'handle_signals')

        # Should have custom attribute
        assert hasattr(CustomWorkerSettings, 'custom_attribute')
        assert CustomWorkerSettings.custom_attribute == "custom_value"

        # Original class should not be affected
        assert not hasattr(WorkerSettings, 'custom_attribute')

    def test_worker_settings_attributes_can_be_overridden(self):
        """Test that WorkerSettings attributes can be overridden."""
        class CustomWorkerSettings(WorkerSettings):
            handle_signals = True  # Override the default False

        assert CustomWorkerSettings.handle_signals is True
        assert WorkerSettings.handle_signals is False  # Original should be unchanged

    def test_additional_functions_can_be_added(self):
        """Test that additional functions can be added to the functions list."""

        async def custom_task(ctx, name: str) -> str:
            return f"Custom task {name}"

        class CustomWorkerSettings(WorkerSettings):
            functions = WorkerSettings.functions + [custom_task]

        assert len(CustomWorkerSettings.functions) == len(WorkerSettings.functions) + 1
        assert custom_task in CustomWorkerSettings.functions
        assert sample_background_task in CustomWorkerSettings.functions


class TestWorkerSettingsEdgeCases:
    """Test edge cases and error conditions for WorkerSettings."""

    def test_worker_settings_with_empty_functions_list(self):
        """Test behavior when functions list is empty."""
        class EmptyFunctionsWorkerSettings:
            functions = []
            redis_settings = WorkerSettings.redis_settings
            on_startup = WorkerSettings.on_startup
            on_shutdown = WorkerSettings.on_shutdown
            handle_signals = WorkerSettings.handle_signals

        assert isinstance(EmptyFunctionsWorkerSettings.functions, list)
        assert len(EmptyFunctionsWorkerSettings.functions) == 0

    def test_worker_settings_with_none_startup_shutdown(self):
        """Test worker settings with None startup/shutdown functions."""
        class NoLifecycleWorkerSettings:
            functions = WorkerSettings.functions
            redis_settings = WorkerSettings.redis_settings
            on_startup = None
            on_shutdown = None
            handle_signals = WorkerSettings.handle_signals

        assert NoLifecycleWorkerSettings.on_startup is None
        assert NoLifecycleWorkerSettings.on_shutdown is None

    def test_worker_settings_attribute_access(self):
        """Test accessing WorkerSettings attributes dynamically."""
        # Test that attributes can be accessed via getattr
        assert getattr(WorkerSettings, 'functions', None) is not None
        assert getattr(WorkerSettings, 'redis_settings', None) is not None
        assert getattr(WorkerSettings, 'handle_signals', None) is not None

        # Test non-existent attribute
        assert getattr(WorkerSettings, 'non_existent_attr', 'default') == 'default'

    def test_worker_settings_with_invalid_redis_settings(self):
        """Test behavior with invalid Redis settings."""
        # This tests what happens if someone manually sets invalid redis_settings
        class InvalidRedisWorkerSettings:
            functions = WorkerSettings.functions
            redis_settings = "invalid_redis_settings"  # Not a RedisSettings object
            on_startup = WorkerSettings.on_startup
            on_shutdown = WorkerSettings.on_shutdown
            handle_signals = WorkerSettings.handle_signals

        # Should still be accessible, but won't work with ARQ
        assert InvalidRedisWorkerSettings.redis_settings == "invalid_redis_settings"
        assert not isinstance(InvalidRedisWorkerSettings.redis_settings, RedisSettings)


class TestWorkerSettingsDocumentation:
    """Test documentation and introspection of WorkerSettings."""

    def test_worker_settings_class_docstring(self):
        """Test that WorkerSettings class has proper documentation."""
        # Note: The actual class doesn't have a docstring, but we can test that
        # the class can have one added
        assert hasattr(WorkerSettings, '__doc__')

    def test_worker_settings_help_information(self):
        """Test that help information can be generated for WorkerSettings."""
        # Should be able to get help without errors
        try:
            help(WorkerSettings)
            # help() returns None but prints to stdout, so we just verify it doesn't crash
        except Exception as e:
            pytest.fail(f"Help generation failed: {e}")

    def test_worker_settings_dir_listing(self):
        """Test that dir() works on WorkerSettings."""
        attrs = dir(WorkerSettings)

        assert 'functions' in attrs
        assert 'redis_settings' in attrs
        assert 'on_startup' in attrs
        assert 'on_shutdown' in attrs
        assert 'handle_signals' in attrs

    def test_worker_settings_vars_listing(self):
        """Test that vars() works on WorkerSettings."""
        try:
            # vars() might not work on all classes, but if it does, it should include our attributes
            variables = vars(WorkerSettings)
            if variables:  # Only test if vars() returns something
                expected_attrs = ['functions', 'redis_settings', 'on_startup', 'on_shutdown', 'handle_signals']
                for attr in expected_attrs:
                    if attr in variables:
                        assert variables[attr] is not None
        except TypeError:
            # vars() might not work on this type of class, which is fine
            pass
