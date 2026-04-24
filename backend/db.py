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
    url = (s.upstash_redis_url or "").strip()
    token = (s.upstash_redis_token or "").strip()
    if not url or not token or not url.startswith("https://"):
        return None
    try:
        from upstash_redis import Redis
        client = Redis(url=url, token=token)
        return client
    except Exception:
        return None
