"""Post-generation NSFW moderation for video outputs."""
from __future__ import annotations

import math
import os
import random
from enum import Enum
from pathlib import Path

NSFW_THRESHOLD = float(os.getenv("NSFW_THRESHOLD", "0.8"))
NSFW_FRAMES_PER_SECOND = int(os.getenv("NSFW_FRAMES_PER_SECOND", "3"))
_detector = None


class NSFWContentDetected(RuntimeError):
    def __init__(self, confidence: float, timestamp: float):
        self.confidence = confidence
        self.timestamp = timestamp
        super().__init__("Video blocked because NSFW content was detected")


def get_detector():
    global _detector
    if _detector is not None:
        return _detector
    import torch
    from nsfw_image_detector import NSFWDetector

    error = None
    for device, dtype in (("cuda", torch.bfloat16), ("cuda", torch.float16), ("cpu", torch.float32)):
        try:
            _detector = NSFWDetector(dtype=dtype, device=device)
            return _detector
        except Exception as exc:
            error = exc
    raise RuntimeError("Unable to initialize NSFW detector") from error


def sampled_video_frames(path: Path):
    """Reservoir-sample up to N distinct frames from every video second."""
    import cv2
    from PIL import Image

    capture = cv2.VideoCapture(str(path))
    try:
        fps = capture.get(cv2.CAP_PROP_FPS)
        expected = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if not capture.isOpened() or not math.isfinite(fps) or fps <= 0:
            raise RuntimeError("Unable to decode video for NSFW moderation")
        second, seen, index, samples = 0, 0, 0, []
        rng = random.SystemRandom()
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_second = math.floor(index / fps)
            if frame_second != second:
                for frame_index, image in sorted(samples):
                    yield frame_index / fps, image
                second, seen, samples = frame_second, 0, []
            seen += 1
            slot = len(samples) if len(samples) < NSFW_FRAMES_PER_SECOND else rng.randrange(seen)
            if slot < NSFW_FRAMES_PER_SECOND:
                item = (index, Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                if len(samples) < NSFW_FRAMES_PER_SECOND:
                    samples.append(item)
                else:
                    samples[slot] = item
            index += 1
        if index == 0 or (math.isfinite(expected) and index < expected - 1):
            raise RuntimeError("Video is empty or could not be decoded completely")
        for frame_index, image in sorted(samples):
            yield frame_index / fps, image
    finally:
        capture.release()


def check_video_nsfw(path: Path) -> None:
    detector = get_detector()
    for timestamp, image in sampled_video_frames(path):
        probabilities = detector.predict_proba(image)
        if isinstance(probabilities, (list, tuple)):
            probabilities = next((item for item in probabilities if isinstance(item, dict)), None)
        if not isinstance(probabilities, dict):
            raise RuntimeError("NSFW detector returned invalid probabilities")
        values = {str(k.value if isinstance(k, Enum) else k): float(v) for k, v in probabilities.items()}
        score = values.get("low")
        if score is None or not math.isfinite(score) or not 0 <= score <= 1:
            raise RuntimeError("NSFW detector returned an invalid LOW score")
        if score >= NSFW_THRESHOLD:
            raise NSFWContentDetected(score, timestamp)

