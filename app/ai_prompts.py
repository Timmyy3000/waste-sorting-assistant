"""All prompts sent to OpenAI, kept in one place so they are easy to read and change."""

CLASSIFY_PROMPT = """You are a household waste sorting assistant.
Look at the photo and classify the main waste item.
Answer ONLY with JSON in this exact shape:
{"category": "<recyclable|compostable|landfill|unknown>", "material": "<short material name>", "confidence": <number between 0 and 1>}
Use "unknown" if the photo does not show a waste item."""

TIP_PROMPT = """Give one short disposal tip for a household waste item.
Category: {category}
Region: {region}
Answer in one or two plain sentences, at most 300 characters."""
