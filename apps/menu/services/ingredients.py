"""Ingredient derivation heuristics (pure functions, no database access).

Ingredients are not first-class in the source XML. They are derived from two
signals: pipe-delimited product descriptions ("turkey | bacon | ...") and
"No X" removal options (ISREMOVALGROUP). The source data contains typos and
singular/plural drift, so derivation is heuristic by design — see DESIGN.md D6.
"""

from dataclasses import dataclass

# Word-level typo fixes observed in the data.
WORD_TYPO_ALIASES = {
    "vegatables": "vegetables",
}

# Whole-phrase singular/plural merges observed in the data.
PHRASE_ALIASES = {
    "banana peppers": "banana pepper",
    "cucumbers": "cucumber",
    "eggs": "egg",
}

ACRONYMS = {
    "Bbq": "BBQ",
}


@dataclass(frozen=True)
class DerivedIngredient:
    display: str
    source: str  # matches ProductIngredient.Source values


def split_description(description: str) -> list[str]:
    """Pipe-delimited descriptions are ingredient lists; prose descriptions are not."""
    if "|" not in description:
        return []
    return [part.strip() for part in description.split("|") if part.strip()]


def strip_removal_prefix(option_name: str) -> str | None:
    name = option_name.strip()
    if name.lower().startswith("no "):
        return name[3:].strip() or None
    return None


def canonical(raw: str) -> str:
    words = [WORD_TYPO_ALIASES.get(word, word) for word in raw.casefold().split()]
    phrase = " ".join(words)
    return PHRASE_ALIASES.get(phrase, phrase)


def display_name(canonical_name: str) -> str:
    words = [word.capitalize() for word in canonical_name.split()]
    return " ".join(ACRONYMS.get(word, word) for word in words)


def derive(description: str, removal_option_names: list[str]) -> dict[str, DerivedIngredient]:
    """Merge both signals into {canonical_name: DerivedIngredient}."""
    sources: dict[str, set[str]] = {}
    for raw in split_description(description):
        sources.setdefault(canonical(raw), set()).add("description")
    for option_name in removal_option_names:
        raw = strip_removal_prefix(option_name)
        if raw is not None:
            sources.setdefault(canonical(raw), set()).add("removal_option")

    derived: dict[str, DerivedIngredient] = {}
    for key, seen_sources in sources.items():
        source = "both" if len(seen_sources) == 2 else next(iter(seen_sources))
        derived[key] = DerivedIngredient(display=display_name(key), source=source)
    return derived
