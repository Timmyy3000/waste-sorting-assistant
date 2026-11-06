"""Conservative German household sorting guidance. AI never invents a bin.

The municipality remains authoritative; rules are reviewed examples for the
three supported cities, not a complete municipal Abfall-ABC.
"""

from dataclasses import dataclass

from app.routes.errors import UploadError


STREAMS = {
    "unknown": "Needs identification",
    "bio": "Bioabfall · food and garden",
    "rest": "Restmüll · residual waste",
    "paper": "Altpapier · paper and cardboard",
    "packaging": "Packaging · plastic, metal, cartons",
    "glass": "Altglas · non-deposit container glass",
    "deposit": "Pfand · returnable bottle or can",
    "electronics": "Electronics and batteries · separate collection",
    "hazardous": "Hazardous waste · special collection",
    "bulky": "Bulky waste · municipal collection",
    "vehicle": "Vehicle or vehicle parts · specialist collection",
}

CATEGORY = {
    "unknown": "unknown", "bio": "compostable", "rest": "landfill",
    "paper": "recyclable", "packaging": "recyclable", "glass": "recyclable",
    "deposit": "recyclable", "electronics": "unknown", "hazardous": "unknown",
    "bulky": "unknown", "vehicle": "unknown",
}

SOURCES = {
    "Dortmund": "https://www.edg.de/de/entsorgungsdienstleistungen/dahin-damit/abfall-abc.htm",
    "Berlin": "https://www.bsr.de/abfall-abc",
    "Munich": "https://www.awm-muenchen.de/abfall-entsorgen/abfall-trennen",
}


@dataclass(frozen=True)
class Guidance:
    bin: str
    instructions: str
    source: str


def guidance(region: str, stream: str) -> Guidance:
    """Return reviewed, qualified guidance, never free-form model advice."""
    if region not in SOURCES or stream not in STREAMS:
        raise UploadError("Choose a supported city and disposal route.")
    source = SOURCES[region]
    common = {
        "unknown": ("Check the city's Abfall-ABC", "Do not choose a bin from an unverified photo. Identify the item and consult the linked municipal guide."),
        "bio": ("Biotonne", "Fruit and vegetable scraps and coffee grounds usually belong here. No plastic or compostable plastic bags. Check local rules for cooked food, meat and bones."),
        "rest": ("Restmülltonne", "For non-recoverable household waste such as used tissues, nappies and broken ceramics. Never put batteries or electronics here."),
        "paper": ("Papiertonne / Blaue Tonne", "Clean paper, flattened cardboard and cartons belong here. Drink cartons and greasy paper do not."),
        "glass": ("Altglascontainer", "Only non-deposit glass bottles and jars. Separate white, brown and green glass; other colours go with green. No drinking glasses, mirrors or ceramics."),
        "deposit": ("Pfand return point", "If the bottle or can carries a deposit, return it to a participating shop or return machine, not a waste container. Check the label first."),
        "electronics": ("Retail take-back / Wertstoffhof", "Return electronic devices and batteries separately to an approved retailer or municipal collection point. Never put them in household bins."),
        "hazardous": ("Schadstoffsammlung", "Paints, solvents and similar hazardous materials need an approved municipal collection point. Check the local Abfall-ABC."),
        "bulky": ("Sperrmüll / Wertstoffhof", "Arrange municipal bulky-waste collection or use an approved recycling centre. Check size and acceptance rules first."),
        "vehicle": ("Authorised vehicle dismantler", "An end-of-life car is not household waste. Ask an authorised end-of-life vehicle collection or dismantling facility; parts, tyres and oils may need separate specialist routes."),
    }
    if stream == "packaging":
        if region == "Munich":
            return Guidance("Wertstoffinsel / local Gelbe Tonne pilot", "Empty plastic, metal and composite packaging goes to local packaging collection. Munich's yellow-bin rollout changes in 2026–27; check your address with AWM before choosing a container. Glass and paper are separate.", source)
        if region == "Berlin":
            return Guidance("Wertstofftonne (yellow/orange)", "Empty plastic, metal and composite packaging, and eligible same-material non-packaging, go here. Not batteries, electronics, glass or paper.", source)
        return Guidance("Wertstofftonne", "Empty plastic, metal and composite packaging goes here. Separate components where possible; no need to wash. Not batteries, electronics, glass or paper.", source)
    return Guidance(*common[stream], source)


def suggestion(category: str, material: str) -> str:
    """Only clearly named items may be suggested; uncertain items need review."""
    if category == "unknown" or not isinstance(material, str):
        return "unknown"
    label = material.strip().lower()
    explicit = {
        "banana peel": "bio", "apple core": "bio", "coffee grounds": "bio",
        "cardboard": "paper", "cardboard box": "paper", "newspaper": "paper",
        "tin can": "packaging", "food tin": "packaging", "yogurt cup": "packaging",
        "used tissue": "rest", "diaper": "rest", "broken ceramic mug": "rest",
    }
    stream = explicit.get(label, "unknown")
    return stream if category == CATEGORY[stream] else "unknown"
