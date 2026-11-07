"""Optional offline image recognition with a small MIT-licensed CLIP model.

Text/image similarity is NOT calibrated confidence. The model identifies likely
objects only; local disposal advice remains unavailable until user confirmation.
Weights live outside Git and are installed explicitly by an administrator.
"""

from functools import lru_cache
from io import BytesIO
from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageOps
from tokenizers import Tokenizer

from app.ai_services import Classification


# A small, conservative vocabulary. The two banana appearances are deliberately
# kept separate so near-ties cannot be presented as an identified peel.
LABELS = (
    ("whole banana", "compostable", "a photograph of a whole yellow banana fruit with its skin still on"),
    ("banana peel", "compostable", "a photograph of a discarded empty banana peel or banana skin"),
    ("cardboard", "recyclable", "a photograph of a cardboard box or flat cardboard sheet"),
    ("newspaper", "recyclable", "a photograph of a sheet of paper or newspaper"),
    ("glass bottle", "recyclable", "a photograph of a glass bottle or a glass jar"),
    ("plastic bottle", "recyclable", "a photograph of a plastic bottle with a cap"),
    ("tin can", "recyclable", "a photograph of a metal food can or tin can"),
    ("plastic wrapper", "recyclable", "a photograph of a plastic food wrapper or snack packet"),
    ("used tissue", "landfill", "a photograph of a used tissue or dirty napkin"),
    ("battery or electronic device", "unknown", "a photograph of a battery or electronic device"),
    ("blank image", "unknown", "a photograph of an empty blank white background without objects"),
    ("food scraps", "compostable", "a photograph of an apple core or discarded food scraps"),
)


class LocalVision:
    """Run ONNX CPU inference without sending the user's photo to a service."""

    def __init__(self, directory: str):
        root = Path(directory)
        self._vision = ort.InferenceSession(
            str(root / "onnx" / "vision_model_quantized.onnx"), providers=["CPUExecutionProvider"]
        )
        text = ort.InferenceSession(
            str(root / "onnx" / "text_model_quantized.onnx"), providers=["CPUExecutionProvider"]
        )
        tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        tokens = tokenizer.encode_batch([entry[2] for entry in LABELS])
        length = max(len(entry.ids) for entry in tokens)
        ids = np.array([entry.ids + [0] * (length - len(entry.ids)) for entry in tokens], dtype=np.int64)
        vectors = text.run(None, {"input_ids": ids})[0]
        self._text_vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)

    def classify(self, image_bytes: bytes) -> Classification:
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        image = ImageOps.fit(image, (224, 224), method=Image.Resampling.BICUBIC)
        pixels = np.asarray(image, dtype=np.float32) / 255.0
        pixels = (pixels - np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)) / np.array(
            [0.26862954, 0.26130258, 0.27577711], dtype=np.float32
        )
        pixels = pixels.transpose(2, 0, 1)[None].astype(np.float32)
        vector = self._vision.run(None, {"pixel_values": pixels})[0]
        vector /= np.linalg.norm(vector, axis=1, keepdims=True)
        scores = (vector @ self._text_vectors.T)[0]
        first, second = np.argsort(-scores)[:2]
        top = LABELS[first]
        runner = LABELS[second]
        score = float(scores[first])

        # A weak or cross-category near-tie gets no category, regardless of the
        # numeric score. Never interpret CLIP similarity as probability.
        if scores[first] < 0.285:
            return Classification("unknown", "unidentified item", 0.0, score)
        if scores[first] - scores[second] < 0.018:
            if {top[0], runner[0]} == {"whole banana", "banana peel"}:
                return Classification("compostable", "banana (whole fruit or peel)", 0.0, score)
            if {top[0], runner[0]} == {"plastic bottle", "glass bottle"}:
                return Classification("recyclable", "bottle (material uncertain)", 0.0, score)
            if top[1] == runner[1] == "recyclable":
                return Classification("recyclable", "recyclable item (material uncertain)", 0.0, score)
            return Classification("unknown", "uncertain item", 0.0, score)
        if top[1] == "unknown":
            return Classification("unknown", top[0], 0.0, score)
        # 0 is a sentinel for "not calibrated", NOT low measured confidence.
        return Classification(top[1], top[0], 0.0, score)


@lru_cache(maxsize=2)
def get_local_vision(directory: str) -> LocalVision:
    return LocalVision(directory)
