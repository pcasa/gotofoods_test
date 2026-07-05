from apps.menu.services import ingredients


def test_pipe_delimited_description_splits_into_ingredients():
    result = ingredients.split_description("turkey | bacon | mozzarella ")
    assert result == ["turkey", "bacon", "mozzarella"]


def test_prose_description_yields_no_ingredients():
    assert ingredients.split_description("A comforting classic.") == []


def test_removal_prefix_stripped_case_insensitively():
    assert ingredients.strip_removal_prefix("No Turkey") == "Turkey"
    assert ingredients.strip_removal_prefix("no bacon") == "bacon"
    assert ingredients.strip_removal_prefix("Normal Option") is None


def test_canonical_fixes_typos_and_plurals():
    assert ingredients.canonical("Chopped Roasted Vegatables") == "chopped roasted vegetables"
    assert ingredients.canonical("Banana Peppers") == "banana pepper"
    assert ingredients.canonical("Eggs") == "egg"


def test_display_name_handles_acronyms():
    assert ingredients.display_name("bbq sauce") == "BBQ Sauce"
    assert ingredients.display_name("banana pepper") == "Banana Pepper"


def test_derive_merges_sources():
    derived = ingredients.derive(
        "turkey | bacon",
        ["No Turkey", "No Eggs", "Not A Removal"],
    )
    assert derived["turkey"].source == "both"
    assert derived["bacon"].source == "description"
    assert derived["egg"].source == "removal_option"
    assert "not a removal" not in derived
