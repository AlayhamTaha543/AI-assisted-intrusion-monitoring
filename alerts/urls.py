from django.urls import path
from .views import AlertListView, AlertDetailView

urlpatterns = [
    path('alerts/', AlertListView.as_view(), name='alert-list'),
    path('alerts/<int:pk>/', AlertDetailView.as_view(), name='alert-detail'),
]
