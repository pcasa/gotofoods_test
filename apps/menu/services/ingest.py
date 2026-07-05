"""Idempotent menu XML ingestion.

Restaurant, categories, and products upsert on external_id; each product's
modifier tree and ingredient links are wiped and rebuilt inside the same
transaction (external IDs are stable, so this is invisible to API clients).
Re-running against the same file yields identical rows.

The full file is 17 MB — a single DOM parse is simpler than streaming and
comfortably fits in memory.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from django.db import transaction

from apps.menu import models
from apps.menu.services import ingredients as ingredient_rules
from core import observability

BULK_BATCH_SIZE = 500


@dataclass(frozen=True)
class IngestResult:
    restaurant: str
    categories: int
    products: int
    option_groups: int
    options: int
    ingredients: int


def _text(value: str | None) -> str:
    return value or ""


def _int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    return int(value)


def _decimal(value: str | None) -> Decimal:
    return Decimal(value) if value else Decimal("0")


def _bool(value: str | None) -> bool:
    return (value or "").lower() == "true"


def _metadata(el: ET.Element) -> dict[str, str]:
    return {d.get("key", ""): d.get("value", "") for d in el.findall("./metadata/data")}


class MenuIngestService:
    def ingest(self, xml_path: Path) -> IngestResult:
        root = ET.parse(xml_path).getroot()
        try:
            with transaction.atomic():
                restaurant = self._upsert_restaurant(root)
                self._replace_hours(restaurant, root)
                totals = self._sync_menu(restaurant, root)
        except Exception as exc:
            observability.error("menu_ingest_failed", exc=exc, source=str(xml_path))
            raise
        observability.info("menu_ingest_completed", source=str(xml_path), **totals)
        return IngestResult(restaurant=restaurant.name, **totals)

    def _upsert_restaurant(self, root: ET.Element) -> models.Restaurant:
        attrs = root.attrib
        restaurant, _ = models.Restaurant.objects.update_or_create(
            external_id=attrs["id"],
            defaults={
                "name": _text(attrs.get("name")),
                "store_name": _text(attrs.get("storename")),
                "brand": _text(attrs.get("brand")),
                "telephone": _text(attrs.get("telephone")),
                "street_address": _text(attrs.get("streetaddress")),
                "city": _text(attrs.get("city")),
                "state": _text(attrs.get("state")),
                "zip_code": _text(attrs.get("zip")),
                "country": _text(attrs.get("country")),
                "latitude": Decimal(attrs["latitude"]) if attrs.get("latitude") else None,
                "longitude": Decimal(attrs["longitude"]) if attrs.get("longitude") else None,
                "attributes": dict(attrs),
            },
        )
        return restaurant

    def _replace_hours(self, restaurant: models.Restaurant, root: ET.Element) -> None:
        restaurant.hours.all().delete()
        models.HoursPeriod.objects.bulk_create(
            models.HoursPeriod(
                restaurant=restaurant,
                handoff_type=_text(el.get("type")),
                day=_text(el.get("day")),
                end_day=_text(el.get("endday")),
                opens=_text(el.get("from")),
                closes=_text(el.get("to")),
            )
            for el in root.findall("./hours/period")
        )

    def _sync_menu(self, restaurant: models.Restaurant, root: ET.Element) -> dict[str, int]:
        totals = {"categories": 0, "products": 0, "option_groups": 0, "options": 0}
        seen_categories: list[str] = []
        seen_products: list[str] = []

        category_sections = (
            ("./menu/categories/category", False),
            ("./menu/singleusecategories/category", True),
        )
        for path, is_single_use in category_sections:
            for cat_el in root.findall(path):
                category, _ = models.Category.objects.update_or_create(
                    external_id=cat_el.get("id"),
                    defaults={
                        "restaurant": restaurant,
                        "name": _text(cat_el.get("name")),
                        "sort_order": _int(cat_el.get("sortorder")) or 0,
                        "is_single_use": is_single_use,
                    },
                )
                seen_categories.append(category.external_id)
                totals["categories"] += 1
                for prod_el in cat_el.findall("./products/product"):
                    product = self._sync_product(category, prod_el, totals)
                    seen_products.append(product.external_id)

        # Remove entries that disappeared from the feed (cascade cleans children).
        models.Product.objects.filter(category__restaurant=restaurant).exclude(
            external_id__in=seen_products
        ).delete()
        restaurant.categories.exclude(external_id__in=seen_categories).delete()

        totals["ingredients"] = models.Ingredient.objects.count()
        return totals

    def _sync_product(
        self, category: models.Category, el: ET.Element, totals: dict[str, int]
    ) -> models.Product:
        product, _ = models.Product.objects.update_or_create(
            external_id=el.get("id"),
            defaults={
                "category": category,
                "chain_external_id": _text(el.get("chainproductid")),
                "name": _text(el.get("name")),
                "description": _text(el.get("description")),
                "short_description": _text(el.get("shortdescription")),
                "cost": _decimal(el.get("cost")),
                "base_calories": _int(el.get("basecalories")),
                "max_calories": _int(el.get("maxcalories")),
                "calories_separator": _text(el.get("caloriesseparator")),
                "is_disabled": _bool(el.get("isdisabled")),
                "sort_order": _int(el.get("sortorder")) or 0,
                "metadata": _metadata(el),
                "images": [dict(img.attrib) for img in el.findall("./images/image")],
            },
        )
        removal_names = self._rebuild_modifier_tree(product, el, totals)
        self._sync_ingredients(product, _text(el.get("description")), removal_names)
        totals["products"] += 1
        return product

    def _rebuild_modifier_tree(
        self, product: models.Product, product_el: ET.Element, totals: dict[str, int]
    ) -> list[str]:
        """Breadth-first rebuild; bulk_create per level (max depth 5 in the data)."""
        product.modifier_groups.all().delete()
        removal_names: list[str] = []
        pending: list[tuple[ET.Element, models.Product | None, models.Option | None]] = [
            (el, product, None) for el in product_el.findall("./modifiers/optiongroup")
        ]
        while pending:
            groups = models.OptionGroup.objects.bulk_create(
                [
                    models.OptionGroup(
                        product=parent_product,
                        parent_option=parent_option,
                        external_id=el.get("id"),
                        chain_external_id=_text(el.get("chainid")),
                        description=_text(el.get("description")),
                        mandatory=_bool(el.get("mandatory")),
                        sort_order=_int(el.get("sortorder")) or 0,
                        metadata=_metadata(el),
                    )
                    for el, parent_product, parent_option in pending
                ],
                batch_size=BULK_BATCH_SIZE,
            )
            option_pairs: list[tuple[ET.Element, models.Option]] = []
            for (group_el, _, _), group in zip(pending, groups, strict=True):
                for opt_el in group_el.findall("./options/option"):
                    metadata = _metadata(opt_el)
                    is_removal = metadata.get("ISREMOVALGROUP", "").lower() == "true"
                    option = models.Option(
                        group=group,
                        external_id=opt_el.get("id"),
                        chain_external_id=_text(opt_el.get("chainid")),
                        name=_text(opt_el.get("name")),
                        cost=_decimal(opt_el.get("cost")),
                        price=(
                            Decimal(price_text)
                            if (price_text := opt_el.findtext("./pricing/price"))
                            else None
                        ),
                        is_default=_bool(opt_el.get("isdefault")),
                        adjusts_parent_calories=_bool(opt_el.get("adjustsparentcalories")),
                        adjusts_parent_price=_bool(opt_el.get("adjustsparentprice")),
                        base_calories=_int(opt_el.get("basecalories")),
                        sort_order=_int(opt_el.get("sortorder")) or 0,
                        is_removal=is_removal,
                        metadata=metadata,
                    )
                    option_pairs.append((opt_el, option))
                    if is_removal:
                        removal_names.append(option.name)
            models.Option.objects.bulk_create(
                [option for _, option in option_pairs], batch_size=BULK_BATCH_SIZE
            )
            totals["option_groups"] += len(groups)
            totals["options"] += len(option_pairs)
            pending = [
                (child_el, None, option)
                for opt_el, option in option_pairs
                for child_el in opt_el.findall("./modifiers/optiongroup")
            ]
        return removal_names

    def _sync_ingredients(
        self, product: models.Product, description: str, removal_names: list[str]
    ) -> None:
        derived = ingredient_rules.derive(description, removal_names)
        product.product_ingredients.all().delete()
        links = []
        for item in derived.values():
            ingredient, _ = models.Ingredient.objects.get_or_create(name=item.display)
            links.append(
                models.ProductIngredient(
                    product=product, ingredient=ingredient, source=item.source
                )
            )
        models.ProductIngredient.objects.bulk_create(links)
