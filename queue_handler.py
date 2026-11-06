import json
import logging
import os
import asyncio
from datetime import datetime

import aio_pika

logger = logging.getLogger(__name__)


class QueueHandler:
    def __init__(self):
        self.connection = None
        self.channel = None
        self.result_exchange = None
        self.type = os.getenv("T2V_TYPE", "process_text_to_video")
        self.publish_timeout = float(os.getenv("RABBITMQ_PUBLISH_TIMEOUT", "15"))
        self.publish_retries = int(os.getenv("RABBITMQ_PUBLISH_RETRIES", "3"))

    async def connect(self):
        url = f"amqp://{os.getenv('RABBITMQ_USER', 'guest')}:{os.getenv('RABBITMQ_PASS', 'guest')}@{os.getenv('RABBITMQ_HOST', 'localhost')}:{os.getenv('RABBITMQ_PORT', '5672')}/"
        self.connection = await aio_pika.connect_robust(url)
        self.channel = await self.connection.channel(publisher_confirms=True)
        await self.channel.set_qos(prefetch_count=int(os.getenv("RABBITMQ_PREFETCH_COUNT", "1")))
        request_exchange = await self.channel.declare_exchange(os.getenv("T2V_EXCHANGE_REQUEST", "TEXT_TO_VIDEO_EXCHANGE_REQUEST"), aio_pika.ExchangeType.HEADERS, durable=True)
        self.result_exchange = await self.channel.declare_exchange(os.getenv("T2V_EXCHANGE_RESULT", "TEXT_TO_VIDEO_EXCHANGE_RESULT"), aio_pika.ExchangeType.HEADERS, durable=True)
        request_queue = await self.channel.declare_queue(os.getenv("T2V_QUEUE_REQUEST", "TEXT_TO_VIDEO_QUEUE_REQUEST"), durable=True)
        result_queue = await self.channel.declare_queue(os.getenv("T2V_QUEUE_RESULT", "TEXT_TO_VIDEO_QUEUE_RESULT"), durable=True)
        await request_queue.bind(request_exchange, arguments={"x-match": "all", "type": self.type})
        await result_queue.bind(self.result_exchange, arguments={"x-match": "all", "type": self.type})
        return request_queue

    async def publish(self, payload: dict):
        payload["timestamp"] = datetime.now().isoformat()
        body = json.dumps(payload, ensure_ascii=False).encode()
        for attempt in range(1, self.publish_retries + 1):
            try:
                message = aio_pika.Message(body, content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT, headers={"type": self.type})
                await self.result_exchange.publish(message, routing_key="", timeout=self.publish_timeout)
                logger.info("Sent result: %s", json.dumps(payload, ensure_ascii=False))
                return True
            except Exception:
                logger.exception("Publish attempt %s/%s failed", attempt, self.publish_retries)
                if attempt < self.publish_retries:
                    await asyncio.sleep(2)
        raise RuntimeError(f"Failed to publish result after {self.publish_retries} attempts")

