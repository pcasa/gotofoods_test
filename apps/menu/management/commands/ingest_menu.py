from pathlib import Path

from django.core.management.base import BaseCommand

from apps.menu.services.ingest import MenuIngestService


class Command(BaseCommand):
    help = "Ingest a menu XML export into the database (idempotent; skips unchanged sources)."

    def add_arguments(self, parser):
        parser.add_argument("xml_path", type=Path)
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-ingest even if the source file is unchanged since the last run.",
        )

    def handle(self, *args, **options):
        result = MenuIngestService().ingest(options["xml_path"], force=options["force"])
        if result.skipped:
            self.stdout.write(f"Skipped {result.restaurant}: source unchanged since last ingest")
            return
        self.stdout.write(
            f"Ingested {result.restaurant}: {result.categories} categories, "
            f"{result.products} products, {result.option_groups} option groups, "
            f"{result.options} options, {result.ingredients} ingredients"
        )
