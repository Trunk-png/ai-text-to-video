import os
import redis.asyncio as redis


class RedisHandler:
    def __init__(self):
        self.ttl = int(os.getenv("REDIS_TTL", "86400"))
        self.client = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=int(os.getenv("REDIS_PORT", "6379")), db=int(os.getenv("REDIS_DB", "0")), password=os.getenv("REDIS_PASSWORD") or None, decode_responses=True)

    async def claim(self, request_id: str) -> bool:
        return bool(await self.client.set(f"t2v:{request_id}", "processing", ex=self.ttl, nx=True))

    async def finish(self, request_id: str, status: str) -> None:
        await self.client.set(f"t2v:{request_id}", status, ex=self.ttl)

    async def release(self, request_id: str) -> None:
        await self.client.delete(f"t2v:{request_id}")

