"""Shared database and cache clients."""

from functools import lru_cache
from typing import Optional
from supabase import create_client, Client
from config import get_settings


@lru_cache
def get_supabase() -> Client:
    s = get_settings()
    return create_client(s.supabase_url, s.supabase_service_role_key)


def get_redis():
    """Returns Redis client or None if not configured."""
    s = get_settings()
    if not s.upstash_redis_url or not s.upstash_redis_token:
        return None
    try:
        from upstash_redis import Redis
        return Redis(url=s.upstash_redis_url, token=s.upstash_redis_token)
    except Exception:
        return None
