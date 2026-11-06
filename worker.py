#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import random
import time
from pathlib import Path

from dotenv import load_dotenv
from langid.langid import LanguageIdentifier, model as langid_model

from comfyui_client import ComfyUIClient
from minio_handler import MinioHandler
from moderation import NSFWContentDetected, check_video_nsfw
from queue_handler import QueueHandler
from redis_handler import RedisHandler

load_dotenv()
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("t2v-worker")
ROOT = Path(__file__).resolve().parent
WORKFLOW_PATH = Path(os.getenv("WORKFLOW_PATH", ROOT / "workflows" / "text_to_video.json"))
LANGUAGE_IDENTIFIER = LanguageIdentifier.from_modelstring(langid_model, norm_probs=True)


class InvalidPromptLanguage(ValueError):
    def __init__(self, detected_language: str):
        self.detected_language = detected_language
        super().__init__("language not support, only support english")


def validate_english_prompt(prompt: str) -> None:
    """Reject prompts that are not classified as English."""
    language, _confidence = LANGUAGE_IDENTIFIER.classify(prompt)
    if language != "en":
        raise InvalidPromptLanguage(language)


def configure_workflow(prompt: str, duration: float | None, seed: int, request_id: str) -> dict:
    workflow = copy.deepcopy(json.loads(WORKFLOW_PATH.read_text(encoding="utf-8")))
    prompt_set = False
    for node in workflow.values():
        inputs = node.setdefault("inputs", {})
        node_type = node.get("class_type")
        if node_type == "LoadImage" or "image" in inputs or "first_frame" in inputs or "last_frame" in inputs:
            raise RuntimeError("Text-to-video workflow must not contain image inputs")
        if node_type == "DetectNSFWText" and isinstance(inputs.get("prompt"), str):
            inputs["prompt"] = prompt
        elif node_type == "MiniMaxH3ImageToVideo" and isinstance(inputs.get("prompt"), (str, list)):
            if isinstance(inputs["prompt"], str):
                inputs["prompt"] = prompt
            prompt_set = True
        elif isinstance(inputs.get("prompt"), str):
            inputs["prompt"] = prompt
            prompt_set = True
        if node_type == "PrimitiveFloat" and node.get("_meta", {}).get("title") == "Float (duration)" and duration is not None:
            inputs["value"] = duration
        if node_type == "RandomNoise":
            inputs["noise_seed"] = seed
        if node_type == "SaveVideo":
            inputs["filename_prefix"] = f"text-to-video/{request_id}"
    if not prompt_set:
        raise RuntimeError("Prompt input was not found in workflow")
    return workflow


class Worker:
    def __init__(self):
        self.queue = QueueHandler()
        self.redis = RedisHandler()
        self.minio = MinioHandler()
        self.comfy = ComfyUIClient(os.getenv("COMFY_URL", "http://127.0.0.1:8188"))
        self.timeout = int(os.getenv("PROCESSING_TIMEOUT", "7200"))
        self.temp = Path(os.getenv("TEMP_DIR", ROOT / "temp"))
        self.temp.mkdir(parents=True, exist_ok=True)

    async def process(self, data: dict) -> dict:
        started = time.monotonic()
        request_id = str(data.get("request_id", "")).strip()
        prompt = str(data.get("prompt", "")).strip()
        if not request_id or len(prompt) < 3:
            raise ValueError("request_id and prompt (at least 3 characters) are required")
        validate_english_prompt(prompt)
        duration = data.get("duration")
        if duration is not None and not 1 <= float(duration) <= 15:
            raise ValueError("duration must be between 1 and 15 seconds")
        seed = int(data.get("seed", random.randrange(2**63)))
        target = self.temp / f"{request_id}.mp4"
        try:
            workflow = configure_workflow(prompt, float(duration) if duration is not None else None, seed, request_id)
            prompt_id = await self.comfy.submit(workflow)
            history = await self.comfy.wait(prompt_id, self.timeout)
            descriptor = self.comfy.find_video(history)
            target = target.with_suffix(Path(descriptor["filename"]).suffix or ".mp4")
            await self.comfy.download_video(descriptor, target)
            await asyncio.to_thread(check_video_nsfw, target)
            output_url = await self.minio.upload(target, request_id)
            return {"request_id": request_id, "status": "success", "status_code": 200, "is_success": True, "output_url": output_url, "seed": seed, "metric": {"duration_seconds": round(time.monotonic() - started, 2)}}
        finally:
            target.unlink(missing_ok=True)

    async def run(self):
        request_queue = await self.queue.connect()
        logger.info("Worker ready; consuming %s", request_queue.name)
        async with request_queue.iterator() as messages:
            async for message in messages:
                async with message.process(requeue=False):
                    request_id = ""
                    try:
                        data = json.loads(message.body)
                        request_id = str(data.get("request_id", ""))
                        if request_id and not await self.redis.claim(request_id):
                            logger.warning("Skipping duplicate request %s", request_id)
                            continue
                        result = await self.process(data)
                        await self.redis.finish(request_id, "success")
                    except InvalidPromptLanguage as exc:
                        result = {"request_id": request_id, "status": "error", "status_code": 422, "is_success": False, "error": {"type": "invalid_prompt_language", "message": str(exc), "details": {"required_language": "en", "detected_language": exc.detected_language}}}
                        if request_id:
                            await self.redis.finish(request_id, "invalid_prompt_language")
                    except NSFWContentDetected as exc:
                        result = {"request_id": request_id, "status": "error", "status_code": 422, "is_success": False, "error": {"type": "nsfw_content_detected", "message": str(exc), "details": {"prediction": "nsfw", "confidence": exc.confidence, "threshold": float(os.getenv("NSFW_THRESHOLD", "0.8")), "timestamp_seconds": round(exc.timestamp, 3)}}}
                        if request_id:
                            await self.redis.finish(request_id, "nsfw_blocked")
                    except Exception as exc:
                        logger.exception("Request %s failed", request_id)
                        result = {"request_id": request_id, "status": "error", "status_code": 500, "is_success": False, "error": {"type": type(exc).__name__, "message": str(exc)}}
                        if request_id:
                            await self.redis.release(request_id)
                    await self.queue.publish(result)


if __name__ == "__main__":
    asyncio.run(Worker().run())

