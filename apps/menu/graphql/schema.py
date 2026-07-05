"""Query root. Fields are declared alphabetically on purpose — GraphiQL's Docs
panel renders them in declaration order. All resolvers are methods (not class
attributes) so declaration order is the schema order."""

import strawberry
import strawberry_django
from graphql.utilities import lexicographic_sort_schema
from strawberry.extensions import QueryDepthLimiter
from strawberry_django.optimizer import DjangoOptimizerExtension

from apps.menu import models
from apps.menu.graphql import types
from apps.menu.services.queries import MenuQueryService


@strawberry.type
class Query:
    @strawberry_django.field(
        description="All menu categories in display order, including single-use "
        "(non-food) sections — filter those client-side via isSingleUse."
    )
    def categories(self) -> list[types.Category]:
        return models.Category.objects.all()  # type: ignore[return-value]

    @strawberry.field(
        description="One category by externalId or case-insensitive exact name."
    )
    def category(
        self, external_id: str | None = None, name: str | None = None
    ) -> types.Category | None:
        return MenuQueryService.category(external_id=external_id, name=name)  # type: ignore[return-value]

    @strawberry_django.field(
        description="All derived ingredients, alphabetical. Navigate to products "
        "to answer 'what on the menu contains this?'"
    )
    def ingredients(self) -> list[types.Ingredient]:
        return models.Ingredient.objects.all()  # type: ignore[return-value]

    @strawberry.field(
        description="One modifier group by externalId. product is set on "
        "root-level groups only; nested groups belong to a parent option."
    )
    def modifier_group(self, external_id: str) -> types.OptionGroup | None:
        return MenuQueryService.modifier_group(external_id=external_id)  # type: ignore[return-value]

    @strawberry.field(
        description="One product by externalId, with its full recursive modifier "
        "tree — nest childGroups in the selection to the depth you need (max 5 in "
        "this menu)."
    )
    def product(self, external_id: str) -> types.Product | None:
        return MenuQueryService.product(external_id=external_id)  # type: ignore[return-value]

    @strawberry.field(
        description="Filtered, searchable, paginated product listing. filter "
        "criteria AND together; search matches name and description "
        "(case-insensitive substring)."
    )
    def products(
        self,
        filter: types.ProductFilter | None = None,
        search: str | None = None,
        first: int = 20,
        offset: int = 0,
    ) -> types.ProductPage:
        criteria = filter or types.ProductFilter()
        items, total = MenuQueryService.products(
            category_external_id=criteria.category_id,
            min_calories=criteria.min_calories,
            max_calories=criteria.max_calories,
            include_ingredients=criteria.include_ingredients,
            exclude_ingredients=criteria.exclude_ingredients,
            available_only=criteria.available_only,
            search=search,
            first=first,
            offset=offset,
        )
        return types.ProductPage(items=items, total_count=total)  # type: ignore[arg-type]

    @strawberry_django.field(
        description="Generic field-level filtering: per-field operators "
        "(iContains, startsWith, gt/gte/lt/lte, range...) on any exposed field, "
        "nestable into category, combinable with AND/OR/NOT. Unlike `products`, "
        "this applies no implicit availability filter — add "
        "isDisabled: { exact: false } if you want only orderable items.",
    )
    def products_advanced(
        self, info: strawberry.Info, filters: types.ProductLookupFilter | None = None
    ) -> list[types.Product]:
        qs = models.Product.objects.all()
        if filters is not None:
            qs = strawberry_django.filters.apply(filters, qs, info)
        return qs  # type: ignore[return-value]

    @strawberry.field(description="Store info, hours by handoff mode, and location.")
    def restaurant(self) -> types.Restaurant | None:
        return MenuQueryService.restaurant()  # type: ignore[return-value]

    @strawberry.field(
        description="Menu-wide search in one round trip: matches products (name "
        "or description), categories, modifier options, and ingredients. Up to "
        "`first` hits per bucket."
    )
    def search(self, term: str, first: int = 10) -> types.MenuSearchResult:
        hits = MenuQueryService.search_menu(term=term, first=first)
        return types.MenuSearchResult(
            categories=hits["categories"],
            products=hits["products"],
            options=hits["options"],
            ingredients=hits["ingredients"],
        )


# The Option <-> OptionGroup recursion makes unbounded-depth queries a DoS
# vector on an unauthenticated endpoint. Sized to the deepest legitimate query:
# a detail view fetching the full 5-level modifier tree via product() = depth 12,
# plus one level of headroom. Deep traversal entered via search (depth 14) is
# deliberately not accommodated - search is a card/list view; details come from
# product(). GraphiQL introspection (~11 deep) must stay under this number.
MAX_QUERY_DEPTH = 13

schema = strawberry.Schema(
    query=Query,
    # Factory (not instance) per strawberry deprecation: a fresh extension is
    # constructed for each request.
    extensions=[DjangoOptimizerExtension, lambda: QueryDepthLimiter(max_depth=MAX_QUERY_DEPTH)],
)
# GraphiQL's "All Schema Types" index lists types in type-map traversal order,
# which declaration order cannot influence. Sort the underlying graphql-core
# schema so the entire Docs panel (type index, fields, args, generated filter
# inputs) reads alphabetically. The sorted copy must carry over the attributes
# strawberry attaches to its GraphQLSchema (e.g. the _strawberry_schema
# back-reference used by strawberry-django at resolve time).
_sorted = lexicographic_sort_schema(schema._schema)
for _attr, _value in vars(schema._schema).items():
    if not hasattr(_sorted, _attr):
        setattr(_sorted, _attr, _value)
schema._schema = _sorted
