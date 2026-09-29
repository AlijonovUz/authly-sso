from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

from .client import PassportClient
from .exceptions import PassportSDKError

User = get_user_model()


def get_passport_client() -> PassportClient:
    return PassportClient(
        base_url=settings.PASSPORT_BASE_URL,
        client_id=settings.PASSPORT_CLIENT_ID,
        client_secret=settings.PASSPORT_CLIENT_SECRET,
        redirect_uri=settings.PASSPORT_REDIRECT_URI,
        timeout=getattr(settings, "PASSPORT_TIMEOUT", 10),
    )


class PassportCallbackAPIView(APIView):
    permission_classes = [AllowAny]

    def get_user_model(self):
        return get_user_model()

    def get_or_create_user(self, user_data: dict):
        """
        Lokal loyiha o'ziga moslab override qilishi uchun asosiy nuqta.
        Standart Django User maydonlari bilan ishlaydi.
        """
        User = self.get_user_model()
        passport_id = user_data.get("passport_id") or user_data.get("id")

        defaults = {
            "email": user_data.get("email") or "",
            "first_name": user_data.get("first_name") or "",
            "last_name": user_data.get("last_name") or "",
        }

        username = f"passport_{passport_id}" if passport_id else user_data.get("username")

        return User.objects.get_or_create(
            username=username,
            defaults=defaults,
        )

    def get_response_data(self, user, user_data: dict, created: bool, tokens: dict) -> dict:
        """Javob qaytarish formati."""
        return {
            "is_new_user": created,
            "user": {
                "id": user.id,
                "passport_id": user_data.get("passport_id") or user_data.get("id"),
                "username": user.username,
                "full_name": f"{user.first_name} {user.last_name}".strip(),
                "email": user.email,
            },
            **tokens,
        }

    def handle_callback(self, request):
        code = request.GET.get("code")
        if not code and hasattr(request, "data") and isinstance(request.data, dict):
            code = request.data.get("code")

        if not code:
            return Response(
                {"error": "Avtorizatsiya kodi ('code') topilmadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = get_passport_client()

        try:
            user_data = client.authenticate_code(code)
        except PassportSDKError as e:
            return Response(
                {"error": str(e), "details": getattr(e, "details", None)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, created = self.get_or_create_user(user_data)

        tokens = {}
        try:
            from rest_framework_simplejwt.tokens import RefreshToken
            refresh = RefreshToken.for_user(user)
            tokens = {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
            }
        except ImportError:
            pass

        return Response(
            self.get_response_data(user, user_data, created, tokens),
            status=status.HTTP_200_OK,
        )

    def get(self, request, *args, **kwargs):
        return self.handle_callback(request)

    def post(self, request, *args, **kwargs):
        return self.handle_callback(request)
