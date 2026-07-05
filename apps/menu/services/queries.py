"""Query-shaping for the API layer.

The modifier tree is recursive (max depth 5 in the data), so single-entity
lookups prefetch the whole tree with one depth-bounded prefetch path —
Django batches one query per level, ~2 x depth queries total regardless of
node count. List queries rely on strawberry-django's optimizer, which builds
prefetches from the GraphQL selection set.
"""

from django.db.models import Q

from apps.menu import models
from apps.menu.services import ingredients as ingredient_rules

MAX_PAGE_SIZE = 100

# One level beyond the observed max depth (5): the boundary level prefetches
# as empty lists instead of triggering per-node queries.
MODIFIER_PREFETCH_DEPTH = 6


def modifier_tree_prefetch(prefix: str = "modifier_groups") -> str:
    return prefix + "__options__child_groups" * MODIFIER_PREFETCH_DEPTH


def _ingredient_display(raw: str) -> str:
    return ingredient_rules.display_name(ingredient_rules.canonical(raw))


class MenuQueryService:
    @staticmethod
    def restaurant() -> models.Restaurant | None:
        return models.Restaurant.objects.prefetch_related("hours").first()

    @staticmethod
    def category(external_id: str | None, name: str | None) -> models.Category | None:
        qs = models.Category.objects.prefetch_related(
            "products__ingredients",
            modifier_tree_prefetch("products__modifier_groups"),
        )
        if external_id is not None:
            qs = qs.filter(external_id=external_id)
        if name is not None:
            qs = qs.filter(name__iexact=name.strip())
        return qs.first()

    @staticmethod
    def products(
        *,
        category_external_id: str | None = None,
        min_calories: int | None = None,
        max_calories: int | None = None,
        include_ingredients: list[str] | None = None,
        exclude_ingredients: list[str] | None = None,
        available_only: bool = True,
        search: str | None = None,
        first: int = 20,
        offset: int = 0,
    ) -> tuple[list[models.Product], int]:
        """Filtered product listing. Returns (page items, total match count).

        Calorie filters compare against base_calories; products without calorie
        data are excluded from calorie-filtered results rather than treated as 0.
        Ingredient terms are normalized with the same rules used at ingest, so
        "eggs" matches the stored "Egg".
        """
        qs = models.Product.objects.select_related("category").prefetch_related("ingredients")
        if available_only:
            qs = qs.filter(is_disabled=False)
        if category_external_id is not None:
            qs = qs.filter(category__external_id=category_external_id)
        if min_calories is not None:
            qs = qs.filter(base_calories__gte=min_calories)
        if max_calories is not None:
            qs = qs.filter(base_calories__lte=max_calories)
        if search:
            term = search.strip()
            qs = qs.filter(Q(name__icontains=term) | Q(description__icontains=term))
        for raw in include_ingredients or []:
            qs = qs.filter(ingredients__name=_ingredient_display(raw))
        if exclude_ingredients:
            qs = qs.exclude(
                ingredients__name__in=[_ingredient_display(raw) for raw in exclude_ingredients]
            )
        qs = qs.distinct()

        total = qs.count()
        first = max(1, min(first, MAX_PAGE_SIZE))
        offset = max(0, offset)
        return list(qs[offset : offset + first]), total

    @staticmethod
    def search_menu(term: str, first: int = 10) -> dict[str, list]:
        """Menu-wide search: matches across products, categories, modifier options,
        and ingredients in one pass. Returns up to `first` rows per bucket."""
        term = term.strip()
        first = max(1, min(first, MAX_PAGE_SIZE))
        if not term:
            return {"categories": [], "products": [], "options": [], "ingredients": []}
        return {
            "categories": list(models.Category.objects.filter(name__icontains=term)[:first]),
            "products": list(
                models.Product.objects.filter(
                    Q(name__icontains=term) | Q(description__icontains=term)
                )
                .select_related("category")
                .prefetch_related("ingredients")[:first]
            ),
            "options": list(models.Option.objects.filter(name__icontains=term)[:first]),
            "ingredients": list(models.Ingredient.objects.filter(name__icontains=term)[:first]),
        }

    @staticmethod
    def modifier_group(external_id: str) -> models.OptionGroup | None:
        subtree = "options" + "__child_groups__options" * MODIFIER_PREFETCH_DEPTH
        return (
            models.OptionGroup.objects.select_related("product", "parent_option")
            .prefetch_related(subtree)
            .filter(external_id=external_id)
            .first()
        )

    @staticmethod
    def product(external_id: str) -> models.Product | None:
        return (
            models.Product.objects.select_related("category")
            .prefetch_related("ingredients", modifier_tree_prefetch())
            .filter(external_id=external_id)
            .first()
        )
