# Redis Pub/Sub Integration for Cache Service

## Overview

The cache service now includes comprehensive Redis pub/sub integration to notify the Rust monitor (oz-multi-tenant) about configuration changes in real-time. This eliminates the need for the monitor to poll for changes every 30 seconds.

## Implementation Details

### 1. Centralized Event Publishing

A new `_publish_cache_event()` helper method provides consistent event publishing across all cache operations:

```python
await cls._publish_cache_event(
    event_type=CacheEventType.UPDATE,
    resource_type=CacheResourceType.MONITOR,
    resource_id=monitor_id,
    tenant_id=tenant_id,
    metadata={...}
)
```

### 2. Event Types

- `CREATE`: New resource cached
- `UPDATE`: Existing resource updated
- `DELETE`: Resource removed from cache
- `INVALIDATE`: Bulk cache invalidation

### 3. Resource Types

- `MONITOR`: Monitor configurations
- `NETWORK`: Network configurations
- `TRIGGER`: Trigger configurations
- `TENANT`: Tenant-level operations
- `PLATFORM`: Platform-wide resources

### 4. Channel Structure

#### Platform Channels

- `blip0:config:update` - General configuration updates
- `blip0:monitor:update` - Monitor-specific updates
- `blip0:network:update` - Network-specific updates
- `blip0:trigger:update` - Trigger-specific updates
- `blip0:platform:update` - Platform-wide updates

#### Tenant-Specific Channels

- `blip0:tenant:{tenant_id}:update` - Tenant-specific updates

### 5. Event Payload Structure

```json
{
  "event_type": "update",
  "resource_type": "monitor",
  "resource_id": "uuid-here",
  "tenant_id": "tenant-uuid",
  "timestamp": "2025-01-14T15:30:00Z",
  "metadata": {
    "active": true,
    "paused": false,
    "validated": true,
    "name": "Monitor Name",
    "slug": "monitor-slug"
  }
}
```

## Integration Points

### Cache Operations with Pub/Sub

1. **Monitor Operations**
   - `cache_monitor()` - Publishes UPDATE event with monitor metadata
   - `delete_monitor()` - Publishes DELETE event

2. **Network Operations**
   - `cache_network()` - Publishes UPDATE event with network metadata
   - `delete_network()` - Publishes DELETE event

3. **Trigger Operations**
   - `cache_trigger()` - Publishes UPDATE event with trigger metadata
   - `delete_trigger()` - Publishes DELETE event

4. **Tenant Operations**
   - `invalidate_tenant_cache()` - Publishes INVALIDATE event with deletion count

## Usage for Rust Monitor (oz-multi-tenant)

The Rust monitor can subscribe to relevant channels and react to changes:

### Example Subscription Strategy

1. **Subscribe to platform channels** for shared resources:

   ```text
   blip0:platform:update
   blip0:network:update (for shared networks)
   ```

2. **Subscribe to tenant-specific channels** for each active tenant:

   ```text
   blip0:tenant:{tenant_id}:update
   ```

3. **Handle events** based on event_type and resource_type:
   - `UPDATE` events: Refresh specific resource from Redis cache
   - `DELETE` events: Remove resource from local cache
   - `INVALIDATE` events: Clear all cached data for tenant

### Example Rust Pseudocode

```rust
// Subscribe to tenant channel
let channel = format!("blip0:tenant:{}:update", tenant_id);
let mut subscriber = redis_conn.subscribe(channel).await?;

// Handle events
while let Some(message) = subscriber.next().await {
    let event: CacheEvent = serde_json::from_str(&message)?;
    
    match (event.event_type, event.resource_type) {
        ("update", "monitor") => {
            // Refresh monitor from Redis
            let monitor = fetch_monitor_from_redis(&event.resource_id).await?;
            update_local_cache(monitor);
        },
        ("delete", "monitor") => {
            // Remove monitor from local cache
            remove_from_local_cache(&event.resource_id);
        },
        ("invalidate", "tenant") => {
            // Clear all tenant data
            clear_tenant_cache(&event.tenant_id);
        },
        _ => {}
    }
}
```

## Testing

A test script is provided at `src/scripts/test_cache_pubsub.py` to verify the integration:

```bash
# Run the test
uv run python -m src.scripts.test_cache_pubsub
```

This script:

1. Subscribes to all cache channels
2. Performs various cache operations
3. Displays received events in real-time
4. Verifies event payload structure

## Benefits

1. **Real-time Updates**: Monitor receives configuration changes immediately
2. **Reduced Latency**: No need to wait for polling intervals
3. **Lower Redis Load**: Eliminates periodic scanning of all keys
4. **Granular Control**: Can subscribe to specific resource types or tenants
5. **Event Metadata**: Rich context for each change event

## Migration Notes

The pub/sub integration is backward compatible. Systems can continue polling while transitioning to event-driven updates. The 30-second cache refresh can remain as a fallback mechanism.
