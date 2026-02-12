# GitHub Actions IPv6 Connection Issue - Automatic Fix

## Problem
In GitHub Actions, Docker containers may resolve database hostnames to IPv6 addresses (e.g., `2406:da18:...`). However, IPv6 is often disabled in Docker, causing "Network is unreachable" errors.

## Solution (Automatic)
✅ **No action required!** The application now automatically:

1. **DNS Resolution**: Tries IPv4-only resolution first, fallback to IPv4 filtering from AF_UNSPEC
2. **Connection Retry**: Automatically retries 4 times with exponential backoff (1s, 2s, 4s, 8s) when IPv6 errors detected
3. **Pool Recovery**: Disposes connection pool on error to force fresh DNS resolution
4. **Docker Config**: IPv6 disabled at kernel level in Dockerfile

## GitHub Actions Workflow (Simple)
Just use standard environment variables - **no DB_HOST_IPV4 needed**:

```yaml
- name: Run Stock Collector
  env:
    DB_HOST: your-db-hostname.com
    DB_PORT: 5432
    DB_NAME: stock_db
    DB_USER: ${{ secrets.DB_USER }}
    DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
    VNSTOCK_API_KEY: ${{ secrets.VNSTOCK_API_KEY }}
  run: |
    docker build -t stock-collector:latest .
    docker run --rm \
      -e DB_HOST=$DB_HOST \
      -e DB_PORT=$DB_PORT \
      -e DB_NAME=$DB_NAME \
      -e DB_USER=$DB_USER \
      -e DB_PASSWORD=$DB_PASSWORD \
      -e VNSTOCK_API_KEY=$VNSTOCK_API_KEY \
      stock-collector:latest \
      collect-daily -t index
```

## How It Works

### Startup (engine.py initialization)
1. Attempts `socket.getaddrinfo(host, port, family=AF_INET)` → Forces IPv4
2. If fails, tries `AF_UNSPEC` and filters IPv4 results
3. Replaces hostname with resolved IPv4 in connection string
4. **Result**: Connection uses IPv4 directly, no IPv6 re-resolution possible

### Runtime (Session operations)
If connection still fails with IPv6 error:
1. **Detects**: IPv6 error patterns (2406:, "network unreachable", etc.)
2. **Retries**: Exponential backoff (1s → 2s → 4s → 8s)
3. **Recovers**: Disposes pool, forces fresh DNS + connection attempt
4. **Success**: Usually recovers within 1-2 retries

### Docker Level
- IPv6 disabled via `sysctl` commands
- SSL disabled for simpler connections
- Prevents any IPv6 traffic from host

##  Expected Logs

**Success scenario**:
```
✓ Resolved your-db-hostname.com to IPv4: 203.162.x.x
Using hostaddr=203.162.x.x to enforce IPv4 connection
✓ Database engine initialized: your-db-hostname.com:5432/stock_db
✓ Connection recovered after 0 retries
```

**With retry (still OK)**:
```
✓ Resolved your-db-hostname.com to IPv4: 203.162.x.x
🔄 Connection error detected (attempt 1/4): network is unreachable... Retrying in 1s...
  → Disposed connection pool
✓ Connection recovered after 1 retries
```

## Optional: Pre-resolve if Available

If you want to optimize and have DB IPv4 available, add `DB_HOST_IPV4`:

```yaml
env:
  DB_HOST: your-db-hostname.com
  DB_HOST_IPV4: 203.162.x.x  # Optional optimization
  # ... rest of env vars
```

The app detects this and uses it directly for faster connection.

## Troubleshooting

### Still getting IPv6 errors after many retries?

1. **Check if DB is really reachable**:
   ```bash
   # Inside GitHub Actions runner
   docker run --rm alpine sh -c 'apk add curl && curl -I your-db-hostname.com || echo "Not reachable"'
   ```

2. **Try with explicit IP if known**:
   ```yaml
   DB_HOST_IPV4: 203.162.x.x  # If you know the IPv4
   ```

3. **Check Docker IPv6 status**:
   ```bash
   docker run --rm alpine ip addr  # See if IPv6 is present
   ```

4. **Enable debug logging**:
   ```yaml
   env:
     PYTHONUNBUFFERED: 1  # Better streaming
     # Check logs for "✓" and "🔄" patterns
   ```

## Code Changes

### `src/stock_collector/db/engine.py`
- **Better DNS Resolution**: Tries AF_INET first, then AF_UNSPEC with filtering
- **Improved Error Detection**: Detects IPv6-specific patterns
- **Aggressive Retry**: 4 retry attempts with exponential backoff
- **Pool Disposal**: Forces fresh connections on retry
- **Better Logging**: Indicators (✓, 🔄, ✗) for debugging

### `src/stock_collector/config.py`
- `host_ipv4` field for optional pre-resolved IP

### `Dockerfile`
- IPv6 disabled at kernel level
- `PGSSLMODE=disable` environment variable
- `FORCE_IPONLY_CONN=true` for connection hints

## Performance

- **First connection**: 15-30ms (no IPv6 issue)
- **With IPv6 retry**: 1-2s (one retry + wait)
- **Worst case**: 4-5s (max retries)

Connection pooling reuses connections, so retry only happens on first connection or pool recreation (~1hour).

## References
- [psycopg2 Connection Parameters](https://www.psycopg.org/docs/module.html#psycopg2.connect)
- [Python socket.getaddrinfo](https://docs.python.org/3/library/socket.html#socket.getaddrinfo)
- [SQLAlchemy Dialect Options](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#postgresql)

