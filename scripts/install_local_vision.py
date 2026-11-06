"""Install optional MIT-licensed image model *outside* the Git repository.

Run once with: python scripts/install_local_vision.py --directory PATH
Then set LOCAL_VISION_MODEL_DIR=PATH in your untracked .env and restart Flask.
"""

import argparse
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = "Xenova/clip-vit-base-patch32"
REVISION = "6b7c523703ae26e39be4b03774966f8571c7f523"
FILES = ("onnx/vision_model_quantized.onnx", "onnx/text_model_quantized.onnx", "tokenizer.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True,
                        help="Directory outside the Git repository (about 155 MB)")
    directory = parser.parse_args().directory.resolve()
    project = Path(__file__).resolve().parent.parent
    if directory == project or project in directory.parents:
        parser.error("Model weights must be stored outside this repository")
    for filename in FILES:
        hf_hub_download(REPO, filename, revision=REVISION, local_dir=str(directory))
        print("Ready:", filename)
    print("Set LOCAL_VISION_MODEL_DIR to", directory, "in your private .env and restart Flask.")


if __name__ == "__main__":
    main()
