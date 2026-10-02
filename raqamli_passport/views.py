from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from .client import PassportClient, verify_webhook_signature
from .exceptions import PassportSDKError
from .services import (
    get_passport_client,
    populate_user_fields,
    find_or_create_user,
    generate_user_jwt_tokens,
    PassportService,
)

User = get_user_model()


class PassportAuthorizeURLAPIView(APIView):
    """
    Frontend uchun Passport SSO login havolasini generatsiya qilib beruvchi endpoint.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        client = get_passport_client()
        scope = request.GET.get("scope", "read")
        state = request.GET.get("state")
        redirect_uri = request.GET.get("redirect_uri")
        final_redirect_uri = redirect_uri or client.redirect_uri

        if not final_redirect_uri:
            return Response(
                {
                    "error": "'redirect_uri' ko'rsatilmadi. So'rovda 'redirect_uri' parametrini yuboring yoki loyiha sozlamalarida PASSPORT_REDIRECT_URI ni belgilang."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            url = client.get_authorization_url(
                scope=scope, state=state, redirect_uri=final_redirect_uri
            )
            return Response({"url": url}, status=status.HTTP_200_OK)
        except PassportSDKError as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class PassportCallbackAPIView(APIView):
    """
    OAuth2 callback uchun tayyor endpoint.
    Frontend yoki SSO provayderidan kelgan 'code' orqali foydalanuvchini tizimga kiritadi.
    """

    permission_classes = [AllowAny]

    def get_user_model(self):
        return get_user_model()

    def get_or_create_user(self, user_data: dict):
        """
        Lokal loyiha o'ziga moslab override qilishi uchun asosiy nuqta.
        """
        return find_or_create_user(self.get_user_model(), user_data)

    def get_response_data(
        self, user, user_data: dict, created: bool, tokens: dict
    ) -> dict:
        """Javob qaytarish formati."""
        return {
            "is_new_user": created,
            "user": {
                "id": user.id,
                "passport_id": user_data.get("passport_id") or user_data.get("id"),
                "username": getattr(user, "username", ""),
                "full_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
                "email": getattr(user, "email", ""),
                "phone": getattr(user, "phone_number", None)
                or getattr(user, "phone", None)
                or user_data.get("phone", ""),
                "avatar": getattr(user, "avatar", None) or user_data.get("avatar", ""),
                "birth_date": getattr(user, "birth_date", None)
                or user_data.get("birth_date", None),
            },
            **tokens,
        }

    def handle_callback(self, request):
        code = request.GET.get("code")
        code_verifier = request.GET.get("code_verifier")
        redirect_uri = request.GET.get("redirect_uri")
        if hasattr(request, "data") and isinstance(request.data, dict):
            if not code:
                code = request.data.get("code")
            if not code_verifier:
                code_verifier = request.data.get("code_verifier")
            if not redirect_uri:
                redirect_uri = request.data.get("redirect_uri")

        if not code:
            return Response(
                {"error": "Avtorizatsiya kodi ('code') topilmadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = get_passport_client()
        final_redirect_uri = redirect_uri or client.redirect_uri

        if not final_redirect_uri:
            return Response(
                {
                    "error": "'redirect_uri' ko'rsatilmadi. So'rovda 'redirect_uri' parametrini yuboring yoki loyiha sozlamalarida PASSPORT_REDIRECT_URI ni belgilang."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_data = client.authenticate_code(
                code, code_verifier=code_verifier, redirect_uri=final_redirect_uri
            )
        except PassportSDKError as e:
            return Response(
                {"error": str(e), "details": getattr(e, "details", None)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user, created = self.get_or_create_user(user_data)
        tokens = self.generate_tokens(user)

        return Response(
            self.get_response_data(user, user_data, created, tokens),
            status=status.HTTP_200_OK,
        )

    def generate_tokens(self, user) -> dict:
        return generate_user_jwt_tokens(user)

    def get(self, request, *args, **kwargs):
        return self.handle_callback(request)

    def post(self, request, *args, **kwargs):
        return self.handle_callback(request)


class PassportWebhookAPIView(APIView):
    """
    Passport serveridan avtomatik o'zgarishlarni qabul qiluvchi Webhook endpoint.
    Foydalanuvchi ma'lumotlari o'zgarganda bazadagi foydalanuvchini avtomatik yangilaydi.
    """

    permission_classes = [AllowAny]

    def get_user_model(self):
        return get_user_model()

    def get_webhook_secret(self) -> str:
        return getattr(settings, "PASSPORT_WEBHOOK_SECRET", "")

    def verify_signature(self, request) -> bool:
        signature = request.headers.get("X-SSO-Signature") or request.META.get(
            "HTTP_X_SSO_SIGNATURE"
        )
        if not signature:
            return False
        secret = self.get_webhook_secret()
        return verify_webhook_signature(secret, request.body, signature)

    def sync_user(self, user_data: dict):
        """
        Lokal loyiha o'ziga moslab override qilishi uchun asosiy nuqta.
        Standart holatda mavjud userni topib ma'lumotlarini yangilaydi.
        """
        user, _ = find_or_create_user(self.get_user_model(), user_data)
        return user

    def post(self, request, *args, **kwargs):
        if not self.verify_signature(request):
            return Response(
                {"error": "Imzo yaroqsiz yoki mavjud emas (Invalid signature)."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        payload = request.data if isinstance(request.data, dict) else {}
        user_data = payload.get("user") or payload
        if not user_data or not isinstance(user_data, dict):
            return Response(
                {"error": "Foydalanuvchi ma'lumotlari topilmadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = self.sync_user(user_data)
        return Response(
            {
                "status": "success",
                "user_id": getattr(user, "id", None),
                "message": "Foydalanuvchi muvaffaqiyatli sinxronlashtirildi.",
            },
            status=status.HTTP_200_OK,
        )


class PassportSyncProfileAPIView(APIView):
    """
    Foydalanuvchi ma'lumotlarini qo'lda (manual) Passport bilan sinxronlashtirish endpointi.
    Login qilgan foydalanuvchi o'z profilini Passport-dan qayta yangilab olishi mumkin.
    """

    permission_classes = [IsAuthenticated]

    def get_access_token(self, request) -> str:
        """
        So'rovdan yoki sessiyadan Passport OAuth access_token-ni oladi.
        Lokal loyiha tokenni o'z saqlash joyiga qarab override qilishi mumkin.
        """
        token = (
            request.data.get("access_token")
            if hasattr(request, "data") and isinstance(request.data, dict)
            else None
        )
        if not token:
            token = request.GET.get("access_token")
        if not token and hasattr(request, "session"):
            token = request.session.get("passport_access_token")
        return token

    def sync_user(self, user, user_data: dict) -> list:
        """
        Lokal loyiha o'ziga moslab override qilishi uchun asosiy nuqta.
        """
        updated_fields = populate_user_fields(user, user_data)
        if updated_fields:
            user.save()
        return updated_fields

    def get_response_data(self, user, user_data: dict) -> dict:
        return {
            "id": user.id,
            "passport_id": user_data.get("passport_id")
            or getattr(user, "passport_id", None),
            "username": getattr(user, "username", ""),
            "full_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
            "email": getattr(user, "email", ""),
            "phone": getattr(user, "phone_number", None)
            or getattr(user, "phone", None)
            or user_data.get("phone", ""),
            "avatar": getattr(user, "avatar", None) or user_data.get("avatar", ""),
            "birth_date": getattr(user, "birth_date", None)
            or user_data.get("birth_date", None),
        }

    def handle_sync(self, request):
        access_token = self.get_access_token(request)

        if access_token:
            client = get_passport_client()
            try:
                user_data = client.get_user_profile(access_token)
            except PassportSDKError as e:
                return Response(
                    {"error": str(e), "details": getattr(e, "details", None)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            updated_fields = self.sync_user(request.user, user_data)
            return Response(
                {
                    "status": "success",
                    "updated_fields": updated_fields,
                    "user": self.get_response_data(request.user, user_data),
                },
                status=status.HTTP_200_OK,
            )

        payload_user = (
            request.data.get("user")
            if hasattr(request, "data") and isinstance(request.data, dict)
            else None
        )
        if payload_user and isinstance(payload_user, dict):
            updated_fields = self.sync_user(request.user, payload_user)
            return Response(
                {
                    "status": "success",
                    "updated_fields": updated_fields,
                    "user": self.get_response_data(request.user, payload_user),
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "error": "Sinxronizatsiya uchun 'access_token' yoki 'user' ma'lumotlari yuborilmadi.",
                "hint": "So'rov parametrida 'access_token' yuboring yoki 'get_access_token' metodini override qiling.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def get(self, request, *args, **kwargs):
        return self.handle_sync(request)

    def post(self, request, *args, **kwargs):
        return self.handle_sync(request)
