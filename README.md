# Menu API — Test for Principal API

Reads the provided menu XML export (restaurant 24405, ~17 MB: 22 categories, 161
products, 24,231 modifier options nested up to 5 levels deep) and serves it as a
**GraphQL API** for menu browsing plus a small **REST** surface for operations.

Stack: Python 3.12 · Django 5 · strawberry-graphql-django · Postgres 16 · Docker Compose.

## Run it

```bash
docker compose up --build
```

First boot runs migrations, ingests the XML (~30–60 s), then serves:

- **GraphiQL** (interactive explorer): http://localhost:8000/graphql
- **Health + row counts**: `GET http://localhost:8000/health`
- **Re-run ingest** (idempotent): `POST http://localhost:8000/internal/ingest`

## Demo queries

Paste into GraphiQL. (Tip: to keep several queries in the editor at once, name
them — `query MenuBoard { ... }` — and pick which to run from the Run button's
dropdown. Anonymous `{ ... }` shorthand only parses when it's alone in the pane.
The Docs panel documents every query, filter, and field.)

**0 — search the whole menu in one round trip** (products by name/description,
plus matching categories, modifier options, and ingredients):

```graphql
{ search(term: "turkey") {
    products { name cost category { name } }
    options { name isRemoval }
    ingredients { name }
    categories { name } } }
```

**1 — the whole menu board in one round trip:**

```graphql
{ categories { name products { name cost baseCalories } } }
```

**2 — one product with its full nested modifier tree** (sizes → removable
ingredients / add-ons → sub-choices; nest `childGroups` as deep as you care to go —
the client controls depth, that's the point of GraphQL here):

```graphql
{ product(externalId: "17794274") {
    name description baseCalories maxCalories
    ingredients { name }
    modifierGroups { description mandatory
      options { name cost isDefault isRemoval
        childGroups { description
          options { name cost isRemoval } } } } } }
```

**3 — a single modifier group as a first-class lookup** (with a back-link to its
owning product when it's a root-level group):

```graphql
{ modifierGroup(externalId: "2562353381") {
    description mandatory
    product { name }
    options { name cost childGroups { description } } } }
```

**4 — dietary filtering: under 600 calories, no bacon:**

```graphql
{ products(filter: { maxCalories: 600, excludeIngredients: ["Bacon"] }, first: 10) {
    totalCount
    items { name baseCalories category { name } ingredients { name } } } }
```

**5 — text search with pagination:**

```graphql
{ products(search: "pizza", first: 5, offset: 0) {
    totalCount items { name cost } } }
```

**6 — restaurant info and hours by handoff mode:**

```graphql
{ restaurant { name city state
    hours { handoffType day opens closes } } }
```

**7 — ingredient-centric navigation: what on the menu contains this?**

```graphql
{ ingredients { name products { name category { name } } } }
```

**8 — must-contain ingredients** (requires ALL terms; input is normalized with the
same rules as ingest, so `"eggs"` matches the stored `Egg`):

```graphql
{ products(filter: { includeIngredients: ["turkey", "bacon"] }) {
    totalCount items { name ingredients { name } } } }
```

**9 — filters compose: calorie band + ingredient exclusion + search + category,
in one query:**

```graphql
{ products(
    filter: { minCalories: 300, maxCalories: 800, excludeIngredients: ["Mayonnaise"] }
    search: "sandwich"
    first: 10
  ) { totalCount items { name baseCalories category { name } } } }
```

**10 — one category by name (case-insensitive) or ID:**

```graphql
{ category(name: "pizzas bogo") { name products { name cost } } }
```

**11 — generic per-field operators** (partial text match, numeric ranges — the
escape hatch when the curated `products` filter doesn't cover a case; supports
`AND`/`OR`/`NOT` and nested category lookups):

```graphql
{ productsAdvanced(filters: {
    name: { iContains: "pizza" }
    baseCalories: { gte: 300, lte: 900 }
    isDisabled: { exact: false }
  }) { name cost baseCalories category { name } } }
```

Or via curl:

```bash
curl -s localhost:8000/graphql -H 'content-type: application/json' \
  -d '{"query":"{ products(search: \"pizza\") { totalCount items { name } } }"}'
```

## Recommended client pattern: cards → detail

The schema permits deep traversal, but consuming apps should split views into
shallow-then-deep queries — list screens fetch card-sized payloads; the heavy
modifier tree is fetched only when a user taps a card. Most cards are never
tapped, so total work stays low. (In production, persisted queries would
enforce this: the app registers its query shapes at build time and the server
executes only those.)

```graphql
# Search screen — one round trip, card-sized payload (depth 4)
query MenuCards($term: String!) {
  products(search: $term, first: 20) {
    totalCount
    items { externalId name cost baseCalories caloriesSeparator category { name } images }
  }
}

# Card tap — full configuration tree for the one product being viewed
query ProductDetail($id: String!) {
  product(externalId: $id) {
    name description baseCalories maxCalories
    ingredients { name }
    modifierGroups { description mandatory
      options { externalId name cost isDefault isRemoval
        childGroups { description options { externalId name cost } } } }
  }
}
```

Set `{ "term": "pizza" }` / `{ "id": "17794274" }` in GraphiQL's Variables panel.
The query depth limit (13) is sized to the worst legitimate case — a detail
view fetching the full 5-level modifier tree via `product()` (depth 12) plus
one level of headroom. Reaching full trees through `search` (depth 14) is
deliberately outside the limit: search serves card views; details come from
`product()`.

## Design in one paragraph

The XML is ingested once (idempotently, keyed on the XML's own IDs — re-running
upserts rather than duplicates) into a normalized schema: category → product →
recursive option-group/option tree, constrained at the DB level. **Ingredients are
derived**, not native to the feed: pipe-delimited descriptions plus "No X" removal
options, normalized through documented heuristics (the feed contains typos and
plural drift — matching is honest-best-effort, and each link records its source).
GraphQL fits the deep, client-shaped menu reads; REST covers health and the ingest
trigger. N+1 on the recursive tree is handled by selection-set-driven query
optimization plus depth-bounded prefetching, enforced by a query-count test.

## Local development (without Docker)

This project takes advantage of ASDF but falls back to what tool you want.

##### ASDF

```bash
asdf plugin add python https://github.com/asdf-community/asdf-python.git
asdf install
```

##### Python VENV

```bash
pyenv install 3.12.8
pyenv local 3.12.8
```

### Python UV

Project also uses `python uv`.  

To install it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install everything.

```bash
uv sync                                  # Python pinned via .python-version / .tool-versions
uv run python manage.py migrate          # SQLite by default; set DATABASE_URL for Postgres
uv run python manage.py ingest_menu 24405.xml
uv run python manage.py runserver
uv run pytest -q                         # fast suite; real-file smoke test: -m slow
uv run ruff check .
```

## Scope notes

Deliberately out of scope (detailed in DESIGN.md §8): ordering/payments, auth on
the read-only menu API, caching, background workers (a one-shot 17 MB file does
not justify a queue — the ingest service boundary is where a feed-driven worker
would attach), and multi-restaurant support (the schema already keys off
restaurant, so it's additive).
