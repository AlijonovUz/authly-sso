from django.urls import path
from .views import (
    PassportAuthorizeURLAPIView,
    PassportCallbackAPIView,
    PassportWebhookAPIView,
    PassportSyncProfileAPIView,
)

app_name = "raqamli_passport"

urlpatterns = [
    path(
        "login-url/", PassportAuthorizeURLAPIView.as_view(), name="passport_login_url"
    ),
    path("callback/", PassportCallbackAPIView.as_view(), name="passport_callback"),
    path("webhook/", PassportWebhookAPIView.as_view(), name="passport_webhook"),
    path("sync/", PassportSyncProfileAPIView.as_view(), name="passport_sync"),
]
