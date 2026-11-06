"""All prompts sent to OpenAI, kept in one place so they are easy to read and change."""

CLASSIFY_PROMPT = """You are inspecting a single uploaded photo for household waste.
Identify only what is actually visible. A whole banana is NOT a discarded banana peel.
Do not infer Pfand, contamination, or a disposal bin from appearance alone.
If you cannot see the image, if several items compete, or if the item is ambiguous, answer unknown.
Low confidence must be used for uncertain descriptions. Do not invent high scores.
Answer ONLY with JSON in this exact shape:
{"category": "<recyclable|compostable|landfill|unknown>", "material": "<short material name>", "confidence": <number between 0 and 1>}
Use "unknown" if the photo does not show a waste item."""

TIP_PROMPT = """Give one short disposal tip for a household waste item.
Category: {category}
Region: {region}
Answer in one or two plain sentences, at most 300 characters."""
