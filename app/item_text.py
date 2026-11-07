"""Small explicit vocabulary for unverified item descriptions.

This is a lookup, not an AI certainty score or a municipal disposal rule.
Unknown and ambiguous text must be reviewed by the user.
"""

import re

from app.ai_services import Classification


ITEMS = {
    "apple": ("apple (whole fruit or scraps)", "compostable"),
    "whole apple": ("apple (whole fruit or scraps)", "compostable"),
    "apple peel": ("apple peel", "compostable"),
    "apfelschale": ("apple peel", "compostable"),
    "apfel": ("apple (whole fruit or scraps)", "compostable"),
    "banana": ("banana (whole fruit or peel)", "compostable"),
    "whole banana": ("banana (whole fruit or peel)", "compostable"),
    "banana peel": ("banana peel", "compostable"),
    "bananenschale": ("banana peel", "compostable"),
    "apple core": ("apple core", "compostable"),
    "coffee grounds": ("coffee grounds", "compostable"),
    "cardboard": ("cardboard", "recyclable"),
    "cardboard box": ("cardboard box", "recyclable"),
    "newspaper": ("newspaper", "recyclable"),
    "tin can": ("tin can", "recyclable"),
    "food tin": ("food tin", "recyclable"),
    "yogurt cup": ("yogurt cup", "recyclable"),
    "plastic bottle": ("plastic bottle", "recyclable"),
    "glass bottle": ("glass bottle", "recyclable"),
    "glass jar": ("glass jar", "recyclable"),
    "used tissue": ("used tissue", "landfill"),
    "diaper": ("diaper", "landfill"),
    "battery": ("battery", "unknown"),
    "phone": ("electronic device", "unknown"),
}


def identify(description: str) -> Classification:
    """Only recognise exact named items; avoid guessing from substring matches."""
    key = re.sub(r"\s+", " ", description.strip().casefold())
    material, category = ITEMS.get(key, (description.strip(), "unknown"))
    return Classification(category, material, 0.0)


def agrees_with_photo(description: str, photo_material: str) -> bool:
    """Require compatible named objects, not merely a matching broad category."""
    claimed = identify(description).material
    seen = identify(photo_material).material
    if claimed == seen:
        return True
    banana = {"banana (whole fruit or peel)", "banana peel"}
    if claimed in banana and seen in banana:
        return True  # the broad label still cannot prove it is a peel
    apple = {"apple (whole fruit or scraps)", "apple peel", "apple core"}
    if claimed in apple and seen in apple:
        return True  # a broad photo cannot prove the exact apple scrap
    return False
