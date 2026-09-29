from django.urls import path
from .views import PassportCallbackAPIView

app_name = "raqamli_passport"

urlpatterns = [
    path("callback/", PassportCallbackAPIView.as_view(), name="passport_callback"),
]