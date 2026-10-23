from django.urls import path
from .views import EventIngestView

urlpatterns = [
    path('events/', EventIngestView.as_view(), name='event-ingest'),
]
