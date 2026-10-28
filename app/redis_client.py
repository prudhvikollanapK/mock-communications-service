from redis.asyncio import Redis
from app.config import REDIS_URL

redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

# Atomically enforce calls-per-second and concurrent-call limits.
# KEYS: active set, cps sorted set. ARGV: call id, now(ms), window(ms),
# cps limit, concurrent limit, active-key TTL seconds.
RESERVE_CALL_LUA = """
local active_key = KEYS[1]
local cps_key = KEYS[2]
local call_id = ARGV[1]
local now = tonumber(ARGV[2])
local window = tonumber(ARGV[3])
local cps_limit = tonumber(ARGV[4])
local concurrent_limit = tonumber(ARGV[5])
local ttl = tonumber(ARGV[6])

redis.call('ZREMRANGEBYSCORE', cps_key, '-inf', now - window)
local active_count = redis.call('SCARD', active_key)
local cps_count = redis.call('ZCARD', cps_key)

if active_count >= concurrent_limit then
  return 1
end
if cps_count >= cps_limit then
  return 2
end

redis.call('SADD', active_key, call_id)
redis.call('EXPIRE', active_key, ttl)
redis.call('ZADD', cps_key, now, call_id)
redis.call('PEXPIRE', cps_key, window * 2)
return 0
"""

def active_key_for(key_hash: str) -> str:
    return f"calls:active:{key_hash}"

def cps_key_for(key_hash: str) -> str:
    return f"calls:cps:{key_hash}"
