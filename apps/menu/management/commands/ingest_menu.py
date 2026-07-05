from pathlib import Path

from django.core.management.base import BaseCommand

from apps.menu.services.ingest import MenuIngestService


class Command(BaseCommand):
    help = "Ingest a menu XML export into the database (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("xml_path", type=Path)

    def handle(self, *args, **options):
        result = MenuIngestService().ingest(options["xml_path"])
        self.stdout.write(
            f"Ingested {result.restaurant}: {result.categories} categories, "
            f"{result.products} products, {result.option_groups} option groups, "
            f"{result.options} options, {result.ingredients} ingredients"
        )
