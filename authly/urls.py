from django.urls import path
from .views import (
    AuthlyAuthorizeURLAPIView,
    AuthlyCallbackAPIView,
    AuthlyWebhookAPIView,
    AuthlySyncProfileAPIView,
)

app_name = "authly"

urlpatterns = [
    path("login-url/", AuthlyAuthorizeURLAPIView.as_view(), name="authly_login_url"),
    path("callback/", AuthlyCallbackAPIView.as_view(), name="authly_callback"),
    path("webhook/", AuthlyWebhookAPIView.as_view(), name="authly_webhook"),
    path("sync/", AuthlySyncProfileAPIView.as_view(), name="authly_sync"),
]
