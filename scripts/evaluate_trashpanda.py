"""Opt-in vision evaluation on a *locally obtained, permission-cleared* dataset.

No dataset download or training occurs. Use an isolated provider quota and do
not interpret broad category agreement as verified municipal disposal advice.
"""

import argparse
import json
import os
import random
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai_services import AIService
from app.config import AppConfig
from app.image_uploads import normalise


EXPECTED = {
    "Biomuell": "compostable",
    "GelberSack": "recyclable",
    "Glass": "recyclable",
    "Papier": "recyclable",
    "Restmuell": "landfill",
    # Special waste cannot safely be mapped into a household bin category.
    "Sondermuell": "unknown",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path, help="Local TrashPanda directory, not a Hugging Face URL")
    parser.add_argument("--per-class", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    if args.per_class < 1 or args.repeats < 1:
        parser.error("per-class and repeats must be positive")
    AppConfig().configure_ai()
    local = bool(os.getenv("LOCAL_VISION_MODEL_DIR"))
    if not local and urlparse(os.getenv("OPENAI_BASE_URL", "")).hostname == "chat.kiconnect.nrw":
        parser.error("The configured KI:connect endpoint failed vision checks; no images were sent")
    service = AIService()
    rng = random.Random(42)
    report = {"source": str(args.dataset), "model": "local CLIP" if local else service.client.model,
              "note": "Coarse dataset agreement only, not item identification or German disposal accuracy.",
              "classes": {}}
    for name, expected in EXPECTED.items():
        candidates = sorted((args.dataset / name).glob("*.jpg"))
        if not candidates:
            parser.error(f"No JPEG images in {args.dataset / name}")
        records = []
        for path in rng.sample(candidates, min(args.per_class, len(candidates))):
            try:
                image = normalise(path.read_bytes())
                predictions = [service.classify_upload(image, "Dortmund") for _ in range(args.repeats)]
                records.append({"file": path.name, "predictions": predictions,
                                "consistent": len({(p["category"], p["material"]) for p in predictions}) == 1})
            except Exception as error:
                records.append({"file": path.name, "error": type(error).__name__})
        report["classes"][name] = {"expected_broad_category": expected,
                                   "records": records}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
