from django.urls import path
from .views import (
    PassportCallbackAPIView,
    PassportWebhookAPIView,
    PassportSyncProfileAPIView,
)

app_name = "raqamli_passport"

urlpatterns = [
    path("callback/", PassportCallbackAPIView.as_view(), name="passport_callback"),
    path("webhook/", PassportWebhookAPIView.as_view(), name="passport_webhook"),
    path("sync/", PassportSyncProfileAPIView.as_view(), name="passport_sync"),
]