import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-insecure-key-do-not-use-in-production")
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "corsheaders",
    "django.contrib.contenttypes",
    "strawberry.django",
    "strawberry_django",
    "apps.menu",
]

MIDDLEWARE = [
    # CORS first so preflight responses short-circuit before other middleware.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
    ),
}

# Browser clients (React apps) on other origins need CORS; native apps and
# curl ignore it. Explicit origins via env; allow-all is for local demos only.
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",") if o]
CORS_ALLOW_ALL_ORIGINS = os.environ.get("CORS_ALLOW_ALL_ORIGINS", "false").lower() == "true"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "app": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "app"},
    },
    "loggers": {
        # Django default config suppresses these on console when DEBUG=false —
        # without this, unhandled REST tracebacks vanish in the container.
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # Strawberry logs resolver exceptions here before masking them into
        # the GraphQL errors payload.
        "strawberry.execution": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # The central app logger used by core.observability. Additional
        # sinks (Datadog/Sentry handlers) attach here — see core/observability.py.
        "app": {
            "handlers": ["console"],
            "level": os.environ.get("LOG_LEVEL", "INFO"),
        },
    },
}

# Menu XML consumed by `manage.py ingest_menu` at container start and by POST /internal/ingest.
MENU_XML_PATH = os.environ.get("MENU_XML_PATH", str(BASE_DIR / "24405.xml"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
TIME_ZONE = "UTC"
USE_TZ = True
