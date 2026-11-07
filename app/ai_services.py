"""Subsystem A – AI Services (owner: Timi).

Classifies a photo of a waste item with the OpenAI vision API and writes a short
disposal tip. The rest of the app only uses AIService and Classification.
"""

import base64
import json
import logging
import os
import random
import time
from dataclasses import replace
from datetime import datetime
from typing import Iterable, Iterator

from app.ai_prompts import CLASSIFY_PROMPT, TIP_PROMPT
from app.pipeline import Processor, ScanEvent, Source

logger = logging.getLogger(__name__)

CATEGORIES = ("recyclable", "compostable", "landfill", "unknown")
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
CONFIDENCE_THRESHOLD = 0.6  # below this the user must confirm the category
MAX_TIP_LENGTH = 300
DEFAULT_MODEL = "gpt-6-luna"


class Classification:
    """The result of classifying one photo."""

    def __init__(self, category: str, material: str, confidence: float):
        # The setters below validate the values.
        self.category = category
        self.material = material
        self.confidence = confidence

    @property
    def category(self) -> str:
        return self._category

    @category.setter
    def category(self, value: str) -> None:
        if value not in CATEGORIES:
            raise ValueError(f"Unknown category: {value!r}")
        self._category = value

    @property
    def material(self) -> str:
        return self._material

    @material.setter
    def material(self, value: str) -> None:
        self._material = value.strip()

    @property
    def confidence(self) -> float:
        return self._confidence

    @confidence.setter
    def confidence(self, value: float) -> None:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"Confidence must be between 0 and 1, got {value}")
        self._confidence = float(value)

    @property
    def needs_confirmation(self) -> bool:
        """True when the AI is unsure, so the user should confirm the category."""
        return self._confidence < CONFIDENCE_THRESHOLD

    def to_dict(self) -> dict:
        return {
            "category": self._category,
            "material": self._material,
            "confidence": self._confidence,
            "needs_confirmation": self.needs_confirmation,
        }

    def __repr__(self) -> str:
        return f"Classification({self._category!r}, {self._material!r}, {self._confidence:.2f})"


class AIClient:
    """Thin wrapper around the OpenAI API. Only this class talks to OpenAI."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        # The key comes from the environment, never from the code.
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._model = model or os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)
        self._client = None  # created on first use (setup method below)

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._model = value

    def connect(self) -> None:
        """Setup method: create the OpenAI client once."""
        if self._client is not None:
            return
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        from openai import OpenAI

        self._client = OpenAI(api_key=self._api_key)

    def call_vision(self, prompt: str, image_bytes: bytes, mime_type: str) -> str:
        """Send a prompt plus an image, return the model's text answer."""
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
        ]
        return self._chat(content, "vision", json_answer=True)

    def call_text(self, prompt: str) -> str:
        """Send a text prompt, return the model's text answer."""
        return self._chat(prompt, "text", json_answer=False)

    def _chat(self, content, kind: str, json_answer: bool) -> str:
        """Shared code for both calls: send the request and log duration + status."""
        self.connect()
        start = time.perf_counter()
        try:
            options = {"response_format": {"type": "json_object"}} if json_answer else {}
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": content}],
                **options,
            )
        except Exception:
            logger.warning("OpenAI %s call failed after %.2fs", kind, time.perf_counter() - start)
            raise
        logger.info("OpenAI %s call ok in %.2fs", kind, time.perf_counter() - start)
        return response.choices[0].message.content


class AIService:
    """What the rest of the app uses: classify a photo and write a disposal tip."""

    def __init__(self, client: AIClient | None = None):
        self._client = client or AIClient()

    @property
    def client(self) -> AIClient:
        return self._client

    @client.setter
    def client(self, value: AIClient) -> None:
        self._client = value

    def classify_image(self, image_bytes: bytes) -> Classification:
        """Check the image, ask the AI (retry once), return a Classification."""
        mime_type = self._check_image(image_bytes)
        answer = self._with_one_retry(
            lambda: self._client.call_vision(CLASSIFY_PROMPT, image_bytes, mime_type)
        )
        data = json.loads(answer)
        category = data.get("category", "unknown")
        if category not in CATEGORIES:
            category = "unknown"
        return Classification(category, data.get("material", ""), float(data.get("confidence", 0.0)))

    def generate_tip(self, category: str, region: str) -> str:
        """Ask the AI for a short disposal tip (max 300 characters)."""
        prompt = TIP_PROMPT.format(category=category, region=region)
        tip = self._with_one_retry(lambda: self._client.call_text(prompt)).strip()
        return tip[:MAX_TIP_LENGTH]

    @staticmethod
    def _check_image(image_bytes: bytes) -> str:
        """Allow only JPEG/PNG up to 5 MB. Returns the MIME type."""
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("Image is larger than 5 MB")
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        raise ValueError("Only JPEG and PNG images are allowed")

    @staticmethod
    def _with_one_retry(call):
        """Run an API call; if it fails, try once more; then give up."""
        try:
            return call()
        except Exception:
            logger.info("Retrying the OpenAI call once")
        try:
            return call()
        except Exception as error:
            raise RuntimeError("AI is not available, please choose the category manually") from error


class ClassificationEventSource(Source):
    """Real source: classifies each incoming photo and yields one ScanEvent per photo.

    `photos` can be any iterable of (image_bytes, region), e.g. uploads arriving over
    time. __iter__ is a generator: it classifies one photo only when the next event is
    requested, so it works on an endless stream.
    """

    def __init__(self, service: AIService, photos: Iterable[tuple[bytes, str]]):
        self._service = service
        self._photos = photos

    def __iter__(self) -> Iterator[ScanEvent]:
        for image_bytes, region in self._photos:
            result = self._service.classify_image(image_bytes)
            yield ScanEvent(datetime.now(), region, result.category, result.material, result.confidence)


class SimulatedScanSource(Source):
    """Demo/test source without OpenAI: produces `count` random scan events.

    Uses the iterator protocol by hand: __iter__ returns the object itself and
    __next__ returns the next event or raises StopIteration at the end.
    """

    def __init__(self, count: int, regions: tuple[str, ...] = ("Dortmund", "Berlin"), seed: int | None = None):
        self._count = count
        self._regions = regions
        self._produced = 0
        self._random = random.Random(seed)  # a seed makes the stream repeatable in tests

    @property
    def produced(self) -> int:
        return self._produced

    def __iter__(self) -> "SimulatedScanSource":
        return self

    def __next__(self) -> ScanEvent:
        if self._produced >= self._count:
            raise StopIteration
        self._produced += 1
        category = self._random.choice(CATEGORIES)
        material = self._random.choice(SAMPLE_MATERIALS[category])
        size = self._random.randint(40, 400)
        return ScanEvent(
            timestamp=datetime.now(),
            region=self._random.choice(self._regions),
            category=category,
            material=material,
            confidence=round(self._random.uniform(0.4, 1.0), 2),
            tags=SAMPLE_TAGS[material],
            bbox=(self._random.randint(0, 600), self._random.randint(0, 400), size, size),
        )


class ConfidenceFilter(Processor):
    """Drops low-confidence predictions so they never reach the sorter.

    Polymorphism: it is a Processor like every other step, so the pipeline runner
    can chain it with `|` without knowing what it does.
    """

    def __init__(self, min_confidence: float = CONFIDENCE_THRESHOLD):
        self.min_confidence = min_confidence  # goes through the setter check
        self._dropped = 0

    @property
    def min_confidence(self) -> float:
        return self._min_confidence

    @min_confidence.setter
    def min_confidence(self, value: float) -> None:
        if not 0 <= value <= 1:
            raise ValueError(f"min_confidence must be between 0 and 1, got {value}")
        self._min_confidence = value

    @property
    def dropped(self) -> int:
        """How many events were filtered out so far."""
        return self._dropped

    def process(self, events: Iterator[ScanEvent]) -> Iterator[ScanEvent]:
        for event in events:  # generator: one event at a time, nothing is stored
            if event.confidence >= self._min_confidence:
                yield event
            else:
                self._dropped += 1


class MaterialRouter(Processor):
    """Turns visual tags and bounding boxes into a material code and a conveyor route.

    Tags such as ("bottle", "clear plastic") become PET; the route tells the
    conveyor which lane to push the item to. Items too big for a lane go to MANUAL.
    """

    def __init__(self, max_box_size: int = 300):
        self._max_box_size = max_box_size

    @property
    def max_box_size(self) -> int:
        return self._max_box_size

    @max_box_size.setter
    def max_box_size(self, value: int) -> None:
        if value <= 0:
            raise ValueError("max_box_size must be positive")
        self._max_box_size = value

    @staticmethod
    def material_code(tags: tuple[str, ...]) -> str:
        """First matching tag wins; unknown tags give OTHER."""
        for tag in tags:
            if tag in TAG_TO_MATERIAL_CODE:
                return TAG_TO_MATERIAL_CODE[tag]
        return "OTHER"

    def process(self, events: Iterator[ScanEvent]) -> Iterator[ScanEvent]:
        for event in events:
            code = self.material_code(event.tags)
            too_big = event.bbox is not None and max(event.bbox[2], event.bbox[3]) > self._max_box_size
            route = "MANUAL" if too_big else MATERIAL_CODE_TO_ROUTE.get(code, "LANE-RESIDUAL")
            yield replace(event, material_code=code, route=route)


SAMPLE_MATERIALS = {
    "recyclable": ("plastic bottle", "milk jug", "tin can", "newspaper", "glass jar"),
    "compostable": ("banana peel", "coffee grounds", "apple core"),
    "landfill": ("chip bag", "broken mug", "used tissue"),
    "unknown": ("unclear item",),
}

# Visual tags an optical sorter would report for each sample material.
SAMPLE_TAGS = {
    "plastic bottle": ("bottle", "clear plastic"),
    "milk jug": ("jug", "milk jug"),
    "tin can": ("can", "aluminium"),
    "newspaper": ("paper", "printed"),
    "glass jar": ("jar", "glass"),
    "banana peel": ("peel", "organic"),
    "coffee grounds": ("grounds", "organic"),
    "apple core": ("fruit", "organic"),
    "chip bag": ("bag", "foil"),
    "broken mug": ("ceramic",),
    "used tissue": ("tissue",),
    "unclear item": (),
}

TAG_TO_MATERIAL_CODE = {
    "clear plastic": "PET",
    "milk jug": "HDPE",
    "aluminium": "ALU",
    "glass": "GLASS",
    "paper": "PAPER",
    "organic": "ORGANIC",
}

MATERIAL_CODE_TO_ROUTE = {
    "PET": "LANE-1-PLASTIC",
    "HDPE": "LANE-1-PLASTIC",
    "ALU": "LANE-2-METAL",
    "GLASS": "LANE-3-GLASS",
    "PAPER": "LANE-4-PAPER",
    "ORGANIC": "LANE-5-ORGANIC",
}


if __name__ == "__main__":
    print("Simulated stream:")
    for event in SimulatedScanSource(count=3, seed=1):
        print(" ", event)

    # Small demo without OpenAI: a fake client returns fixed answers.
    class FakeClient(AIClient):
        def call_vision(self, prompt, image_bytes, mime_type):
            return '{"category": "recyclable", "material": "plastic bottle", "confidence": 0.62}'

        def call_text(self, prompt):
            return "Rinse the bottle and put it in the yellow bin."

    service = AIService(FakeClient(api_key="fake"))
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    result = service.classify_image(png)
    print(result, "needs confirmation:", result.needs_confirmation)
    print(service.generate_tip(result.category, "Dortmund"))
