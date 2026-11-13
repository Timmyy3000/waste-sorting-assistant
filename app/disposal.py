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
        "unknown": ("Check the city's Abfall-ABC", "Do not choose a bin from an unverified result. Identify the item and consult the linked municipal guide."),
        "bio": ("Biotonne", "Discarded fruit, vegetable scraps and coffee grounds usually belong here. Do not throw away edible food unnecessarily. No plastic or compostable plastic bags. Check local rules for cooked food, meat and bones."),
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


# Reviewed item names and their route. The vision prompt (ai_prompts.ITEM_LABELS)
# asks the model to answer with one of these names, so common items get a
# preselected route. Anything else stays "unknown" and the user chooses.
REVIEWED_ITEMS = {
    # bio
    "banana": "bio", "banana peel": "bio", "banana (whole fruit or peel)": "bio", "apple": "bio",
    "apple (whole fruit or scraps)": "bio", "apple peel": "bio", "apple core": "bio",
    "orange peel": "bio", "fruit scraps": "bio", "vegetable scraps": "bio",
    "coffee grounds": "bio", "tea bag": "bio", "eggshells": "bio",
    # paper
    "cardboard": "paper", "cardboard box": "paper", "newspaper": "paper",
    "magazine": "paper", "paper bag": "paper", "egg carton": "paper",
    # packaging
    "tin can": "packaging", "food tin": "packaging", "yogurt cup": "packaging",
    "plastic food tray": "packaging", "plastic packaging film": "packaging",
    "plastic shopping bag": "packaging", "aluminium foil": "packaging",
    "drink carton": "packaging",
    # Pfand: single-use drink cans and plastic drink bottles carry a deposit in Germany
    "drink can": "deposit", "plastic drink bottle": "deposit",
    # glass
    "glass jar": "glass",
    # special collection
    "battery": "electronics", "phone charger": "electronics", "light bulb": "hazardous",
    # residual waste
    "used tissue": "rest", "diaper": "rest", "broken ceramic mug": "rest",
    "disposable coffee cup": "rest", "cigarette butt": "rest", "vacuum cleaner bag": "rest",
}


def suggestion(category: str, material: str) -> str:
    """Only clearly named items may be suggested; uncertain items need review."""
    if not isinstance(material, str):
        return "unknown"
    stream = REVIEWED_ITEMS.get(material.strip().lower(), "unknown")
    return stream if category == CATEGORY[stream] else "unknown"
