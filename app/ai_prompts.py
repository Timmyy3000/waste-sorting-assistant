"""All prompts sent to OpenAI, kept in one place so they are easy to read and change."""

# Item names the app has reviewed routes for (see disposal.REVIEWED_ITEMS).
ITEM_LABELS = {
    "compostable": ["banana", "banana peel", "apple", "apple core", "orange peel", "fruit scraps",
                    "vegetable scraps", "coffee grounds", "tea bag", "eggshells"],
    "recyclable": ["cardboard", "cardboard box", "newspaper", "magazine", "paper bag", "egg carton",
                   "food tin", "yogurt cup", "plastic food tray", "plastic packaging film",
                   "plastic shopping bag", "aluminium foil", "drink carton", "drink can",
                   "plastic drink bottle", "glass jar"],
    "landfill": ["used tissue", "diaper", "broken ceramic mug", "disposable coffee cup",
                 "cigarette butt", "vacuum cleaner bag"],
    # special collection, never a household bin
    "unknown": ["battery", "phone charger", "light bulb"],
}
_LABEL_LINES = "\n".join(f"- {category}: {', '.join(labels)}" for category, labels in ITEM_LABELS.items())

CLASSIFY_PROMPT = """You are inspecting a single uploaded photo for household waste.
Identify only what is actually visible.
Do not infer Pfand, contamination, or a disposal bin from appearance alone.
If you cannot see the image, if several items compete, or if the item is ambiguous, answer unknown.
Low confidence must be used for uncertain descriptions. Do not invent high scores.
Answer ONLY with JSON in this exact shape:
{"category": "<recyclable|compostable|landfill|unknown>", "material": "<short material name>", "confidence": <number between 0 and 1>}
Use "unknown" if the photo does not show a waste item.
If the item clearly matches one of these known items, use that exact name as "material"
and the category it is listed under; otherwise give a short material name:
""" + _LABEL_LINES

TIP_PROMPT = """Give one short disposal tip for a household waste item.
Category: {category}
Region: {region}
Answer in one or two plain sentences, at most 300 characters."""
