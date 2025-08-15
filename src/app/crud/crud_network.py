"""
Enhanced CRUD operations for network management with RPC validation.
"""

import asyncio
import json
from datetime import UTC, datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def create_with_validation(
        self,
        db: AsyncSession,
        obj_in: NetworkCreate,
        validate_rpcs: bool = True
    ) -> NetworkRead:
        """
        Create network with optional RPC validation.

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

        # Create network
        network_data = NetworkCreateInternal(**obj_in.model_dump())
        network = Network(**network_data.model_dump())

        # Set validation status
        if validation_errors:
            network.validated = False
            network.validation_errors = validation_errors
        else:
            network.validated = True
            network.last_validated_at = datetime.now(UTC)

        db.add(network)
        await db.flush()
        await db.refresh(network)

        return NetworkRead.model_validate(network)

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

    async def cache_to_redis(
        self,
        db: AsyncSession,
        redis_client: Any,
        network_id: Any
    ) -> None:
        """
        Cache network configuration to Redis for Rust monitor.

        Args:
            db: Database session
            redis_client: Redis client
            network_id: Network ID
        """
        query = select(Network).where(Network.id == network_id)
        result = await db.execute(query)
        network = result.scalar_one_or_none()

        if network and network.active:
            # Cache key following schema design
            cache_key = f"platform:networks:{network.slug}"

            # Prepare network data for caching
            network_data = {
                "id": str(network.id),
                "name": network.name,
                "slug": network.slug,
                "network_type": network.network_type,
                "chain_id": network.chain_id,
                "network_passphrase": network.network_passphrase,
                "rpc_urls": network.rpc_urls,
                "block_time_ms": network.block_time_ms,
                "confirmation_blocks": network.confirmation_blocks,
                "cron_schedule": network.cron_schedule,
                "max_past_blocks": network.max_past_blocks,
                "store_blocks": network.store_blocks,
            }

            await redis_client.set(
                cache_key,
                json.dumps(network_data, default=str),
                ex=1800  # 30 minute TTL
            )

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
