"""Small async ComfyUI API client for text-to-video."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from urllib.parse import urlencode

import aiohttp


class ComfyUIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client_id = str(uuid.uuid4())

    async def submit(self, workflow: dict) -> str:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.base_url}/prompt", json={"prompt": workflow, "client_id": self.client_id}) as response:
                body = await response.json()
                if response.status != 200 or body.get("node_errors"):
                    raise RuntimeError(json.dumps(body, ensure_ascii=False))
                return body["prompt_id"]

    async def wait(self, prompt_id: str, timeout: int) -> dict:
        deadline = asyncio.get_running_loop().time() + timeout
        async with aiohttp.ClientSession() as session:
            while asyncio.get_running_loop().time() < deadline:
                async with session.get(f"{self.base_url}/history/{prompt_id}") as response:
                    response.raise_for_status()
                    history = (await response.json()).get(prompt_id)
                if history:
                    status = history.get("status", {})
                    if status.get("status_str") == "error":
                        raise RuntimeError(self._execution_error(status.get("messages", [])))
                    if status.get("completed"):
                        return history
                await asyncio.sleep(2)
        raise TimeoutError(f"ComfyUI timed out after {timeout} seconds")

    async def download_video(self, descriptor: dict, target: Path) -> None:
        query = urlencode({"filename": descriptor["filename"], "subfolder": descriptor.get("subfolder", ""), "type": descriptor.get("type", "output")})
        target.parent.mkdir(parents=True, exist_ok=True)
        timeout = aiohttp.ClientTimeout(total=900)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(f"{self.base_url}/view?{query}") as response:
                response.raise_for_status()
                with target.open("wb") as stream:
                    async for chunk in response.content.iter_chunked(1024 * 1024):
                        stream.write(chunk)

    @staticmethod
    def find_video(history: dict) -> dict:
        for output in history.get("outputs", {}).values():
            for key in ("videos", "video", "gifs", "images", "files"):
                values = output.get(key, [])
                if isinstance(values, dict):
                    values = [values]
                for value in values:
                    if isinstance(value, dict) and str(value.get("filename", "")).lower().endswith((".mp4", ".webm", ".mov", ".mkv")):
                        return value
        raise RuntimeError("ComfyUI completed without a video output")

    @staticmethod
    def _execution_error(messages: list) -> str:
        for event in reversed(messages):
            if isinstance(event, (list, tuple)) and len(event) == 2 and event[0] == "execution_error":
                return str(event[1].get("exception_message", "ComfyUI execution failed"))
        return "ComfyUI execution failed"

