import json
from pathlib import Path

import pytest

from apps.menu.services.ingest import MenuIngestService

FIXTURE = Path(__file__).parent / "fixtures" / "menu_sample.xml"

PRODUCT_TREE_QUERY = """
{
  product(externalId: "1001") {
    name
    baseCalories
    ingredients { name }
    modifierGroups {
      description
      options {
        name
        isRemoval
        childGroups {
          description
          options {
            name
            isRemoval
            childGroups {
              description
              options { name }
            }
          }
        }
      }
    }
  }
}
"""


@pytest.fixture
def ingested(db):
    MenuIngestService().ingest(FIXTURE)


def gql(client, query: str) -> dict:
    response = client.post(
        "/graphql", data=json.dumps({"query": query}), content_type="application/json"
    )
    assert response.status_code == 200
    payload = response.json()
    assert "errors" not in payload, payload.get("errors")
    return payload["data"]


def test_menu_board_categories_and_products(ingested, client):
    data = gql(client, "{ categories { name isSingleUse products { name cost } } }")
    names = [category["name"] for category in data["categories"]]
    assert names == ["Sandwiches", "Beverages", "Utensils"]
    assert [c["isSingleUse"] for c in data["categories"]] == [False, False, True]
    sandwich_names = [p["name"] for p in data["categories"][0]["products"]]
    assert sandwich_names == ["Turkey Capri", "Plain Soup"]


def test_product_full_modifier_tree(ingested, client):
    product = gql(client, PRODUCT_TREE_QUERY)["product"]
    assert product["baseCalories"] == 500

    size = product["modifierGroups"][0]
    assert size["description"] == "Size"
    small = size["options"][0]
    assert small["name"] == "Small"

    child_descriptions = [group["description"] for group in small["childGroups"]]
    assert child_descriptions == ["Remove Ingredients:", "Add-ons"]

    removal = small["childGroups"][0]["options"][0]
    assert removal["name"] == "No Turkey"
    assert removal["isRemoval"] is True

    avocado = small["childGroups"][1]["options"][0]
    assert avocado["childGroups"][0]["description"] == "Amount"
    assert avocado["childGroups"][0]["options"][0]["name"] == "Extra"

    ingredient_names = {i["name"] for i in product["ingredients"]}
    assert {"Turkey", "Bacon", "Egg"} <= ingredient_names


def test_product_tree_is_batched_not_n_plus_one(
    ingested, client, django_assert_max_num_queries
):
    with django_assert_max_num_queries(20):
        gql(client, PRODUCT_TREE_QUERY)


def test_category_lookup_by_name(ingested, client):
    data = gql(client, '{ category(name: "beverages") { name products { name } } }')
    assert data["category"]["name"] == "Beverages"
    assert data["category"]["products"][0]["name"] == "Iced Tea"


def test_restaurant_info_and_hours(ingested, client):
    data = gql(client, "{ restaurant { name city hours { handoffType opens closes } } }")
    assert data["restaurant"]["city"] == "Round Rock"
    assert len(data["restaurant"]["hours"]) == 2


def test_products_filter_contract(ingested, client):
    data = gql(
        client,
        """
        { products(
            filter: { maxCalories: 600, excludeIngredients: ["Bacon"] }
            first: 10
          ) {
            totalCount
            items { name baseCalories ingredients { name } }
        } }
        """,
    )
    page = data["products"]
    assert page["totalCount"] == 1
    assert page["items"][0]["name"] == "Iced Tea"


def test_products_search_contract(ingested, client):
    data = gql(client, '{ products(search: "capri") { totalCount items { name } } }')
    assert data["products"]["items"][0]["name"] == "Turkey Capri"


def test_modifier_group_top_level_lookup(ingested, client):
    data = gql(
        client,
        """
        { modifierGroup(externalId: "9001") {
            description
            mandatory
            product { name }
            options { name childGroups { description } }
        } }
        """,
    )
    group = data["modifierGroup"]
    assert group["description"] == "Size"
    assert group["mandatory"] is True
    assert group["product"]["name"] == "Turkey Capri"
    small = group["options"][0]
    assert [g["description"] for g in small["childGroups"]] == ["Remove Ingredients:", "Add-ons"]

    # Nested groups belong to a parent option, not directly to a product.
    nested = gql(client, '{ modifierGroup(externalId: "9002") { product { name } } }')
    assert nested["modifierGroup"]["product"] is None


def test_ingredient_to_products_navigation(ingested, client):
    data = gql(client, '{ ingredients { name products { name category { name } } } }')
    by_name = {i["name"]: i["products"] for i in data["ingredients"]}
    assert by_name["Bacon"][0]["name"] == "Turkey Capri"
    assert by_name["Bacon"][0]["category"]["name"] == "Sandwiches"


def test_products_advanced_field_lookups(ingested, client):
    data = gql(
        client,
        """
        { productsAdvanced(filters: {
            name: { iContains: "capri" }
            baseCalories: { gte: 100, lte: 600 }
          }) { name baseCalories } }
        """,
    )
    assert [p["name"] for p in data["productsAdvanced"]] == ["Turkey Capri"]

    data = gql(
        client,
        '{ productsAdvanced(filters: { baseCalories: { gt: 600 } }) { name } }',
    )
    assert data["productsAdvanced"] == []


def test_menu_wide_search(ingested, client):
    data = gql(
        client,
        """
        { search(term: "turkey") {
            products { name }
            options { name isRemoval }
            ingredients { name }
            categories { name }
        } }
        """,
    )
    hits = data["search"]
    assert hits["products"][0]["name"] == "Turkey Capri"
    assert {"name": "No Turkey", "isRemoval": True} in hits["options"]
    assert hits["ingredients"] == [{"name": "Turkey"}]
    assert hits["categories"] == []


def test_full_configurator_depth_is_within_limit(ingested, client):
    """Canary: the deepest legitimate query — a detail view fetching all 5
    modifier levels via product() (depth 12) — must pass the depth limit.
    Fails if the limit is tightened below what the data requires."""
    selection = "name"
    for _ in range(4):  # levels 2-5; level 1 comes from modifierGroups/options
        selection = f"childGroups {{ options {{ {selection} }} }}"
    query = f'{{ product(externalId: "1001") {{ modifierGroups {{ options {{ {selection} }} }} }} }}'
    gql(client, query)  # asserts no errors


def test_excessively_deep_query_is_rejected(ingested, client):
    """The recursive modifier schema is depth-limited (DoS guard). Legitimate
    full-tree queries pass (covered above); a 40-plus-deep query must not."""
    selection = "name"
    for _ in range(20):
        selection = f"childGroups {{ options {{ {selection} }} }}"
    query = f'{{ product(externalId: "1001") {{ modifierGroups {{ options {{ {selection} }} }} }} }}'

    response = client.post(
        "/graphql", data=json.dumps({"query": query}), content_type="application/json"
    )
    payload = response.json()
    assert payload.get("data") is None
    assert any("depth" in e["message"].lower() for e in payload["errors"])


def test_schema_type_index_is_alphabetical(client):
    data = gql(client, "{ __schema { types { name } } }")
    names = [t["name"] for t in data["__schema"]["types"] if not t["name"].startswith("__")]
    assert names == sorted(names)


def test_query_fields_are_alphabetical(client):
    """Docs-panel convention: GraphiQL renders fields in declaration order,
    so Query fields must be declared alphabetically."""
    data = gql(client, '{ __type(name: "Query") { fields { name } } }')
    names = [field["name"] for field in data["__type"]["fields"]]
    assert names == sorted(names)


def test_unknown_product_returns_null(ingested, client):
    data = gql(client, '{ product(externalId: "does-not-exist") { name } }')
    assert data["product"] is None
