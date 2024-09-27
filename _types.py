import asyncpg

try:
    from asyncpg.pool import PoolConnectionProxy
except ImportError:
    PoolConnectionProxy = asyncpg.Connection  # type: ignore

connection_type = asyncpg.Connection | PoolConnectionProxy
