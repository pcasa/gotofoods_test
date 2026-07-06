from django.db import models


class Restaurant(models.Model):
    external_id = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    store_name = models.CharField(max_length=255, blank=True)
    brand = models.CharField(max_length=255, blank=True)
    telephone = models.CharField(max_length=32, blank=True)
    street_address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=128, blank=True)
    state = models.CharField(max_length=32, blank=True)
    zip_code = models.CharField(max_length=16, blank=True)
    country = models.CharField(max_length=8, blank=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return self.name


class HoursPeriod(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="hours")
    handoff_type = models.CharField(max_length=32)
    day = models.CharField(max_length=16)
    end_day = models.CharField(max_length=16, blank=True)
    # "24:00" appears in the data, so these cannot be TimeFields.
    opens = models.CharField(max_length=8)
    closes = models.CharField(max_length=8)

    class Meta:
        ordering = ["handoff_type", "id"]

    def __str__(self) -> str:
        return f"{self.handoff_type} {self.day} {self.opens}-{self.closes}"


class Category(models.Model):
    restaurant = models.ForeignKey(Restaurant, on_delete=models.CASCADE, related_name="categories")
    external_id = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255, db_index=True)
    sort_order = models.IntegerField(default=0)
    # The feed has two category sections: <categories> and <singleusecategories>
    # (utensils and similar non-food items).
    is_single_use = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name_plural = "categories"

    def __str__(self) -> str:
        return self.name


class Ingredient(models.Model):
    name = models.CharField(max_length=128, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products")
    external_id = models.CharField(max_length=32, unique=True)
    chain_external_id = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    short_description = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=9, decimal_places=4)
    base_calories = models.PositiveIntegerField(null=True, blank=True)
    max_calories = models.PositiveIntegerField(null=True, blank=True)
    calories_separator = models.CharField(max_length=8, blank=True)
    is_disabled = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    images = models.JSONField(default=list, blank=True)
    ingredients = models.ManyToManyField(
        Ingredient, through="ProductIngredient", related_name="products"
    )

    class Meta:
        ordering = ["sort_order", "id"]
        indexes = [models.Index(fields=["base_calories"])]

    def __str__(self) -> str:
        return self.name


class OptionGroup(models.Model):
    external_id = models.CharField(max_length=32, unique=True)
    chain_external_id = models.CharField(max_length=64, blank=True)
    description = models.CharField(max_length=255, blank=True)
    mandatory = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, null=True, blank=True, related_name="modifier_groups"
    )
    parent_option = models.ForeignKey(
        "Option", on_delete=models.CASCADE, null=True, blank=True, related_name="child_groups"
    )

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.CheckConstraint(
                name="optiongroup_exactly_one_parent",
                condition=(
                    models.Q(product__isnull=False, parent_option__isnull=True)
                    | models.Q(product__isnull=True, parent_option__isnull=False)
                ),
            ),
        ]

    def __str__(self) -> str:
        return self.description


class Option(models.Model):
    group = models.ForeignKey(OptionGroup, on_delete=models.CASCADE, related_name="options")
    external_id = models.CharField(max_length=32, unique=True)
    chain_external_id = models.CharField(max_length=64, blank=True)
    name = models.CharField(max_length=255, db_index=True)
    cost = models.DecimalField(max_digits=9, decimal_places=4)
    price = models.DecimalField(max_digits=9, decimal_places=4, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    adjusts_parent_calories = models.BooleanField(default=False)
    adjusts_parent_price = models.BooleanField(default=False)
    base_calories = models.PositiveIntegerField(null=True, blank=True)
    sort_order = models.IntegerField(default=0)
    is_removal = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.name


class IngestRun(models.Model):
    """Audit record per ingest attempt. The latest completed run's source_hash
    is the skip-if-unchanged guard for container restarts."""

    class Status(models.TextChoices):
        COMPLETED = "completed"
        SKIPPED = "skipped"
        FAILED = "failed"

    source = models.CharField(max_length=255)
    source_hash = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.status} {self.source_hash[:12]}"


class ProductIngredient(models.Model):
    class Source(models.TextChoices):
        DESCRIPTION = "description"
        REMOVAL_OPTION = "removal_option"
        BOTH = "both"

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="product_ingredients"
    )
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="product_links"
    )
    source = models.CharField(max_length=16, choices=Source.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product", "ingredient"], name="unique_product_ingredient"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product} - {self.ingredient} ({self.source})"
