"""
Enhanced CRUD operations for network management with RPC validation and Redis caching.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logging
from ..core.redis_client import redis_client
from ..models.network import Network
from ..schemas.network import (
    NetworkCreate,
    NetworkCreateInternal,
    NetworkDelete,
    NetworkFilter,
    NetworkRead,
    NetworkRPCAdd,
    NetworkRPCRemove,
    NetworkRPCTest,
    NetworkRPCTestResult,
    NetworkSort,
    NetworkUpdate,
    NetworkUpdateInternal,
    NetworkValidationRequest,
    NetworkValidationResult,
)
from .base import EnhancedCRUD

logger = logging.getLogger(__name__)


class CRUDNetwork(
    EnhancedCRUD[
        Network,
        NetworkCreateInternal,
        NetworkUpdate,
        NetworkUpdateInternal,
        NetworkDelete,
        NetworkRead,
        NetworkFilter,
        NetworkSort
    ]
):
    """
    Enhanced CRUD operations for Network model with RPC validation.
    Includes RPC health checks, network validation, and caching for Rust monitor.
    """

    async def create_with_caching(
        self,
        db: AsyncSession,
        obj_in: NetworkCreate,
        validate_rpcs: bool = False
    ) -> NetworkRead:
        """
        Create network with write-through caching.
        Networks are platform-managed resources.

        Args:
            db: Database session
            obj_in: Network creation data
            validate_rpcs: Whether to validate RPC URLs

        Returns:
            Created network
        """
        # Validate RPCs if requested
        validation_errors = {}
        if validate_rpcs and obj_in.rpc_urls:
            for rpc in obj_in.rpc_urls:
                test_result = await self._test_rpc_url(
                    rpc["url"],
                    obj_in.network_type,
                    obj_in.chain_id
                )
                if not test_result.is_online:
                    validation_errors[rpc["url"]] = test_result.error

        # Create network internal object
        network_internal = NetworkCreateInternal(**obj_in.model_dump())

        # Create using parent CRUD
        db_network = await self.create(db=db, object=network_internal)

        # Set validation status
        if validation_errors:
            db_network.validated = False
            db_network.validation_errors = validation_errors
        else:
            db_network.validated = True
            db_network.last_validated_at = datetime.now(UTC)

        await db.flush()
        await db.refresh(db_network)

        # Write-through to Redis for fast access by Rust monitor
        await self._cache_network(db_network)

        logger.info(f"Created platform network {db_network.slug}")
        return NetworkRead.model_validate(db_network)

    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
        tenant_id: Optional[Any] = None
    ) -> Optional[Network]:
        """
        Get network by slug.

        Args:
            db: Database session
            slug: Network slug
            tenant_id: Optional tenant ID for multi-tenant isolation

        Returns:
            Network if found, None otherwise
        """
        query = select(Network).where(Network.slug == slug)

        # Apply tenant filter if provided
        if tenant_id is not None:
            query = query.where(Network.tenant_id == tenant_id)

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def validate_network(
        self,
        db: AsyncSession,
        validation_request: NetworkValidationRequest
    ) -> NetworkValidationResult:
        """
        Validate network configuration and RPC connectivity.

        Args:
            db: Database session
            validation_request: Validation request

        Returns:
            Validation result
        """
        errors: list[str] = []
        warnings: list[str] = []
        rpc_status: dict[str, Any] = {}

        # Get network
        query = select(Network).where(
            Network.id == validation_request.network_id)
        result = await db.execute(query)
        network = result.scalar_one_or_none()

        if not network:
            errors.append("Network not found")
            return NetworkValidationResult(
                network_id=validation_request.network_id,
                is_valid=False,
                errors=errors,
                warnings=warnings,
                rpc_status=rpc_status
            )

        # Validate required fields
        if not network.rpc_urls:
            errors.append("Network must have at least one RPC URL")

        # Test RPC connections if requested
        current_block_height = None
        if validation_request.test_connection and network.rpc_urls:
            test_tasks = []
            for rpc in network.rpc_urls:
                test_tasks.append(
                    self._test_rpc_url(
                        rpc["url"],
                        network.network_type,
                        network.chain_id
                    )
                )

            test_results = await asyncio.gather(*test_tasks)

            for i, test_result in enumerate(test_results):
                rpc_url = network.rpc_urls[i]["url"]
                rpc_status[rpc_url] = {
                    "online": test_result.is_online,
                    "latency_ms": test_result.latency_ms,
                    "error": test_result.error
                }

                if test_result.is_online and test_result.block_height:
                    current_block_height = max(
                        current_block_height or 0,
                        test_result.block_height
                    )

            # Check if at least one RPC is online
            online_rpcs = [s for s in rpc_status.values() if s["online"]]
            if not online_rpcs:
                errors.append("No RPC URLs are reachable")

        # Validate network-specific requirements
        if network.network_type == "EVM" and not network.chain_id:
            errors.append("EVM networks must have a chain_id")
        elif network.network_type == "Stellar" and not network.network_passphrase:
            errors.append("Stellar networks must have a network_passphrase")

        # Update network validation status
        network.validated = len(errors) == 0
        network.validation_errors = {
            "errors": errors,
            "warnings": warnings,
            "rpc_status": rpc_status
        }
        network.last_validated_at = datetime.now(UTC)

        await db.flush()

        return NetworkValidationResult(
            network_id=validation_request.network_id,
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            rpc_status=rpc_status,
            current_block_height=current_block_height
        )

    async def add_rpc_urls(
        self,
        db: AsyncSession,
        rpc_add: NetworkRPCAdd
    ) -> Optional[NetworkRead]:
        """
        Add RPC URLs to a network.

        Args:
            db: Database session
            rpc_add: RPC URLs to add

        Returns:
            Updated network or None
        """
        query = select(Network).where(Network.id == rpc_add.network_id)
        result = await db.execute(query)
        network = result.scalar_one_or_none()

        if not network:
            return None

        # Add new RPC URLs
        existing_urls = {rpc["url"] for rpc in network.rpc_urls}
        for new_rpc in rpc_add.rpc_urls:
            if new_rpc["url"] not in existing_urls:
                network.rpc_urls.append(new_rpc)

        network.updated_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(network)

        return NetworkRead.model_validate(network)

    async def remove_rpc_urls(
        self,
        db: AsyncSession,
        rpc_remove: NetworkRPCRemove
    ) -> Optional[NetworkRead]:
        """
        Remove RPC URLs from a network.

        Args:
            db: Database session
            rpc_remove: RPC URLs to remove

        Returns:
            Updated network or None
        """
        query = select(Network).where(Network.id == rpc_remove.network_id)
        result = await db.execute(query)
        network = result.scalar_one_or_none()

        if not network:
            return None

        # Remove specified RPC URLs
        network.rpc_urls = [
            rpc for rpc in network.rpc_urls
            if rpc["url"] not in rpc_remove.rpc_urls
        ]

        network.updated_at = datetime.now(UTC)
        await db.flush()
        await db.refresh(network)

        return NetworkRead.model_validate(network)

    async def test_rpc_url(
        self,
        rpc_test: NetworkRPCTest
    ) -> NetworkRPCTestResult:
        """
        Test an RPC URL for connectivity and functionality.

        Args:
            rpc_test: RPC test parameters

        Returns:
            Test result
        """
        return await self._test_rpc_url(
            rpc_test.url,
            rpc_test.network_type,
            rpc_test.chain_id
        )

    async def get_active_networks(
        self,
        db: AsyncSession,
        tenant_id: Optional[Any] = None
    ) -> list[NetworkRead]:
        """
        Get all active networks.

        Args:
            db: Database session
            tenant_id: Optional tenant filter

        Returns:
            List of active networks
        """
        query = select(Network).where(
            Network.active == True,  # noqa: E712
            Network.validated == True  # noqa: E712
        )

        if tenant_id:
            query = query.where(Network.tenant_id == tenant_id)

        result = await db.execute(query)
        networks = result.scalars().all()

        return [NetworkRead.model_validate(n) for n in networks]

    async def get_with_cache(
        self,
        db: AsyncSession,
        network_id: Any,
        use_cache: bool = True,
    ) -> Optional[NetworkRead]:
        """
        Get a network by ID with cache support.

        Args:
            db: Database session
            network_id: Network ID
            use_cache: Whether to try cache first

        Returns:
            Network if found
        """
        # Try cache first if enabled
        if use_cache:
            cached = await self._get_cached_network_by_id(str(network_id))
            if cached:
                logger.debug(f"Cache hit for network {network_id}")
                return cached

        # Fallback to database
        db_network = await self.get(db=db, id=network_id)

        if not db_network:
            return None

        # Refresh cache on cache miss
        if use_cache:
            await self._cache_network(db_network)

        return NetworkRead.model_validate(db_network)

    async def get_by_slug_with_cache(
        self,
        db: AsyncSession,
        slug: str,
        use_cache: bool = True,
    ) -> Optional[NetworkRead]:
        """
        Get a network by slug with cache support.
        Slug is the primary identifier used by Rust monitor.

        Args:
            db: Database session
            slug: Network slug
            use_cache: Whether to try cache first

        Returns:
            Network if found
        """
        # Try cache first if enabled
        if use_cache:
            cached = await self._get_cached_network_by_slug(slug)
            if cached:
                logger.debug(f"Cache hit for network slug {slug}")
                return cached

        # Fallback to database
        db_network = await self.get_by_slug(db=db, slug=slug)

        if not db_network:
            return None

        # Refresh cache on cache miss
        if use_cache:
            await self._cache_network(db_network)

        return NetworkRead.model_validate(db_network)

    async def update_with_cache(
        self,
        db: AsyncSession,
        network_id: Any,
        obj_in: NetworkUpdate,
    ) -> Optional[NetworkRead]:
        """
        Update a network with cache invalidation.

        Args:
            db: Database session
            network_id: Network ID
            obj_in: Update data

        Returns:
            Updated network if found
        """
        # Get existing network to find slug for cache invalidation
        existing = await self.get(db=db, id=network_id)
        if not existing:
            return None

        old_slug = str(existing.slug) if existing and hasattr(existing, 'slug') else ""  # type: ignore[attr-defined]

        # Update in PostgreSQL
        db_network = await self.update(
            db=db,
            object=obj_in,
            id=network_id
        )

        if not db_network:
            return None

        # Invalidate old cache entries
        await self._invalidate_network_cache(old_slug, str(network_id))

        # Refresh cache with new data
        await self._cache_network(db_network)

        if hasattr(db_network, 'slug'):
            logger.info(f"Updated platform network {db_network.slug}")  # type: ignore[attr-defined]
        else:
            logger.info(f"Updated platform network {network_id}")
        return NetworkRead.model_validate(db_network)

    async def delete_with_cache(
        self,
        db: AsyncSession,
        network_id: Any,
        is_hard_delete: bool = False,
    ) -> bool:
        """
        Delete a network with cache cleanup.

        Args:
            db: Database session
            network_id: Network ID
            is_hard_delete: If True, permanently delete

        Returns:
            True if deleted successfully
        """
        # Get network for slug before deletion
        existing = await self.get(db=db, id=network_id)
        if not existing:
            return False

        slug = str(existing.slug) if existing and hasattr(existing, 'slug') else ""  # type: ignore[attr-defined]

        # Delete from PostgreSQL
        deleted = False
        try:
            await self.delete(
                db=db,
                id=network_id,
                is_hard_delete=is_hard_delete
            )
            deleted = True
        except Exception:
            deleted = False

        if deleted:
            # Remove from cache
            await self._invalidate_network_cache(slug, str(network_id))
            logger.info(f"Deleted platform network {slug}")

        return bool(deleted)

    async def refresh_all_networks(
        self,
        db: AsyncSession
    ) -> int:
        """
        Refresh all platform networks in Redis cache.
        Used for periodic cache refresh or manual sync.

        Args:
            db: Database session

        Returns:
            Number of networks refreshed
        """
        # Get all networks
        result = await self.get_multi(db=db, return_total_count=False)
        # get_multi returns a dict with 'data' key containing list
        networks: list[Any] = []
        if isinstance(result, dict):
            data = result.get("data", [])
            if isinstance(data, list):
                networks = data

        # Clear existing cache
        pattern = "platform:networks:*"
        await redis_client.delete_pattern(pattern)
        pattern = "platform:network:id:*"
        await redis_client.delete_pattern(pattern)

        # Re-cache all networks
        count = 0
        for network in networks:
            if network:  # Ensure network is not None
                await self._cache_network(network)
                count += 1

        logger.info(f"Refreshed {count} platform networks in cache")
        return count

    async def get_all_network_slugs(
        self,
        db: AsyncSession
    ) -> list[str]:
        """
        Get all network slugs for quick lookups.

        Args:
            db: Database session

        Returns:
            List of network slugs
        """
        result = await self.get_multi(db=db, return_total_count=False)
        # get_multi returns a dict with 'data' key containing list
        networks: list[Any] = []
        if isinstance(result, dict):
            data = result.get("data", [])
            if isinstance(data, list):
                networks = data
        return [str(network.slug) for network in networks if network and hasattr(network, 'slug')]

    # Redis caching helper methods
    async def _cache_network(self, network: Any) -> None:
        """
        Cache network in Redis with platform-managed key pattern.
        Uses both ID and slug for different access patterns.
        """
        try:
            # Cache by slug (primary access pattern for Rust monitor)
            slug_key = f"platform:networks:{network.slug}"
            network_dict = NetworkRead.model_validate(
                network).model_dump_json()

            # Cache for 1 hour (networks change infrequently)
            await redis_client.set(slug_key, network_dict, expiration=3600)

            # Also cache by ID for admin operations
            id_key = f"platform:network:id:{network.id}"
            await redis_client.set(id_key, network_dict, expiration=3600)

        except Exception as e:
            logger.error(f"Failed to cache network {network.slug}: {e}")

    async def _get_cached_network_by_slug(self, slug: str) -> Optional[NetworkRead]:
        """Get network from cache by slug."""
        try:
            import json
            key = f"platform:networks:{slug}"
            cached = await redis_client.get(key)

            if cached:
                if isinstance(cached, str):
                    cached = json.loads(cached)
                return NetworkRead.model_validate(cached)
            return None
        except Exception as e:
            logger.error(f"Failed to get cached network by slug {slug}: {e}")
            return None

    async def _get_cached_network_by_id(self, network_id: str) -> Optional[NetworkRead]:
        """Get network from cache by ID."""
        try:
            import json
            key = f"platform:network:id:{network_id}"
            cached = await redis_client.get(key)

            if cached:
                if isinstance(cached, str):
                    cached = json.loads(cached)
                return NetworkRead.model_validate(cached)
            return None
        except Exception as e:
            logger.error(
                f"Failed to get cached network by ID {network_id}: {e}")
            return None

    async def _invalidate_network_cache(self, slug: str, network_id: str) -> None:
        """Invalidate network cache entries."""
        try:
            slug_key = f"platform:networks:{slug}"
            id_key = f"platform:network:id:{network_id}"
            await redis_client.delete(slug_key, id_key)
        except Exception as e:
            logger.error(f"Failed to invalidate network cache {slug}: {e}")

    async def bulk_validate(
        self,
        db: AsyncSession,
        network_ids: list[Any]
    ) -> dict[str, NetworkValidationResult]:
        """
        Validate multiple networks in parallel.

        Args:
            db: Database session
            network_ids: List of network IDs

        Returns:
            Dictionary of validation results by network ID
        """
        tasks = []
        for network_id in network_ids:
            request = NetworkValidationRequest(
                network_id=network_id,
                test_connection=True,
                check_block_height=True
            )
            tasks.append(self.validate_network(db, request))

        results = await asyncio.gather(*tasks)

        return {
            str(network_ids[i]): results[i]
            for i in range(len(network_ids))
        }

    # Private helper methods

    async def _test_rpc_url(
        self,
        url: str,
        network_type: str,
        chain_id: Optional[int] = None
    ) -> NetworkRPCTestResult:
        """
        Test RPC URL connectivity and functionality.

        Args:
            url: RPC URL to test
            network_type: Network type (EVM or Stellar)
            chain_id: Expected chain ID for EVM

        Returns:
            Test result
        """
        start_time = datetime.now(UTC)
        is_online = False
        block_height = None
        error = None

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                if network_type == "EVM":
                    # Test EVM RPC
                    response = await client.post(
                        url,
                        json={
                            "jsonrpc": "2.0",
                            "method": "eth_blockNumber",
                            "params": [],
                            "id": 1
                        }
                    )
                    response.raise_for_status()
                    data = response.json()

                    if "result" in data:
                        is_online = True
                        # Convert hex to int
                        block_height = int(data["result"], 16)

                    # Check chain ID if provided
                    if chain_id and is_online:
                        chain_response = await client.post(
                            url,
                            json={
                                "jsonrpc": "2.0",
                                "method": "eth_chainId",
                                "params": [],
                                "id": 2
                            }
                        )
                        chain_data = chain_response.json()
                        if "result" in chain_data:
                            actual_chain_id = int(chain_data["result"], 16)
                            if actual_chain_id != chain_id:
                                error = f"Chain ID mismatch: expected {chain_id}, got {actual_chain_id}"
                                is_online = False

                elif network_type == "Stellar":
                    # Test Stellar RPC
                    response = await client.get(f"{url}/ledgers?limit=1&order=desc")
                    response.raise_for_status()
                    data = response.json()

                    if "_embedded" in data and "records" in data["_embedded"]:
                        records = data["_embedded"]["records"]
                        if records:
                            is_online = True
                            block_height = records[0].get("sequence")

        except httpx.TimeoutException:
            error = "Connection timeout"
        except httpx.HTTPError as e:
            error = f"HTTP error: {str(e)}"
        except Exception as e:
            error = f"Test failed: {str(e)}"

        # Calculate latency
        latency_ms = int(
            (datetime.now(UTC) - start_time).total_seconds() * 1000)

        return NetworkRPCTestResult(
            url=url,
            is_online=is_online,
            latency_ms=latency_ms if is_online else None,
            block_height=block_height,
            error=error
        )


# Export crud instance
crud_network = CRUDNetwork(Network)
