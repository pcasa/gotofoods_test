from django.conf import settings
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from strawberry.django.views import GraphQLView

from apps.menu.api.views import health, trigger_ingest
from apps.menu.graphql.schema import schema

urlpatterns = [
    path("health", health, name="health"),
    path("internal/ingest", trigger_ingest, name="trigger-ingest"),
    path(
        "graphql",
        csrf_exempt(GraphQLView.as_view(
            schema=schema,
            graphql_ide="graphiql" if settings.GRAPHIQL_ENABLED else None,
        )),
        name="graphql",
    ),
]
