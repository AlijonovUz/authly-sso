from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated

from .client import PassportClient, verify_webhook_signature
from .exceptions import PassportSDKError

User = get_user_model()


def get_passport_client() -> PassportClient:
    backend_url = (
        getattr(settings, "PASSPORT_BACKEND_URL", None)
        or getattr(settings, "PASSPORT_BASE_URL", "")
    )
    frontend_url = getattr(settings, "PASSPORT_FRONTEND_URL", None) or backend_url

    return PassportClient(
        backend_url=backend_url,
        frontend_url=frontend_url,
        client_id=getattr(settings, "PASSPORT_CLIENT_ID", ""),
        client_secret=getattr(settings, "PASSPORT_CLIENT_SECRET", ""),
        redirect_uri=getattr(settings, "PASSPORT_REDIRECT_URI", ""),
        timeout=getattr(settings, "PASSPORT_TIMEOUT", 10),
        webhook_secret=getattr(settings, "PASSPORT_WEBHOOK_SECRET", None),
    )


def populate_user_fields(user, user_data: dict) -> list:
    """
    Passport-dan kelgan ma'lumotlarni User obyektiga moslab to'ldiradi.
    Viloyat (region) va tuman (district) ID-lar loyihalarda har xil bo'lgani sababli
    avtomatik bog'lanmaydi (buni lokal loyiha kerak bo'lsa override qilib qo'shishi mumkin).

    User modelida mavjud bo'lgan barcha mos maydonlar avtomatik to'ldiriladi:
    - first_name, last_name, email
    - phone / phone_number
    - avatar
    - birth_date
    - passport_id
    """
    updated_fields = []

    passport_id = user_data.get("passport_id") or user_data.get("id")
    if passport_id and hasattr(user, "passport_id") and getattr(user, "passport_id") != passport_id:
        user.passport_id = passport_id
        updated_fields.append("passport_id")

    first_name = user_data.get("first_name") or ""
    if hasattr(user, "first_name") and getattr(user, "first_name") != first_name:
        user.first_name = first_name
        updated_fields.append("first_name")

    last_name = user_data.get("last_name") or ""
    if hasattr(user, "last_name") and getattr(user, "last_name") != last_name:
        user.last_name = last_name
        updated_fields.append("last_name")

    email = user_data.get("email") or ""
    if hasattr(user, "email") and getattr(user, "email") != email:
        user.email = email
        updated_fields.append("email")

    phone = user_data.get("phone") or user_data.get("phone_number") or ""
    if phone:
        if hasattr(user, "phone_number") and getattr(user, "phone_number") != phone:
            user.phone_number = phone
            updated_fields.append("phone_number")
        elif hasattr(user, "phone") and getattr(user, "phone") != phone:
            user.phone = phone
            updated_fields.append("phone")

    avatar = user_data.get("avatar") or ""
    if avatar and hasattr(user, "avatar") and getattr(user, "avatar") != avatar:
        user.avatar = avatar
        updated_fields.append("avatar")

    birth_date = user_data.get("birth_date")
    if birth_date and hasattr(user, "birth_date") and getattr(user, "birth_date") != birth_date:
        user.birth_date = birth_date
        updated_fields.append("birth_date")

    return updated_fields


def find_or_create_user(user_model, user_data: dict):
    """
    Passport ma'lumotlari orqali foydalanuvchini topadi yoki yangi yaratadi.
    """
    passport_id = user_data.get("passport_id") or user_data.get("id")
    user = None

    if passport_id and hasattr(user_model, "passport_id"):
        user = user_model.objects.filter(passport_id=passport_id).first()

    if not user and passport_id and hasattr(user_model, "username"):
        user = user_model.objects.filter(username=f"passport_{passport_id}").first()

    phone = user_data.get("phone") or user_data.get("phone_number")
    if not user and phone:
        if hasattr(user_model, "phone_number"):
            user = user_model.objects.filter(phone_number=phone).first()
        elif hasattr(user_model, "phone"):
            user = user_model.objects.filter(phone=phone).first()

    email = user_data.get("email")
    if not user and email and hasattr(user_model, "email"):
        user = user_model.objects.filter(email=email).first()

    if user:
        created = False
        updated = populate_user_fields(user, user_data)
        if updated:
            user.save()
        return user, created

    created = True
    user = user_model()
    if hasattr(user, "username"):
        user.username = f"passport_{passport_id}" if passport_id else (user_data.get("username") or phone or email)

    populate_user_fields(user, user_data)
    if hasattr(user, "set_unusable_password"):
        user.set_unusable_password()

    user.save()
    return user, created


class PassportAuthorizeURLAPIView(APIView):
    """
    Frontend uchun Passport SSO login havolasini generatsiya qilib beruvchi endpoint.
    """
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        client = get_passport_client()
        scope = request.GET.get("scope", "read")
        state = request.GET.get("state")
        url = client.get_authorization_url(scope=scope, state=state)
        return Response({"url": url}, status=status.HTTP_200_OK)


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

    def get_response_data(self, user, user_data: dict, created: bool, tokens: dict) -> dict:
        """Javob qaytarish formati."""
        return {
            "is_new_user": created,
            "user": {
                "id": user.id,
                "passport_id": user_data.get("passport_id") or user_data.get("id"),
                "username": getattr(user, "username", ""),
                "full_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
                "email": getattr(user, "email", ""),
                "phone": getattr(user, "phone_number", None) or getattr(user, "phone", None) or user_data.get("phone", ""),
                "avatar": getattr(user, "avatar", None) or user_data.get("avatar", ""),
                "birth_date": getattr(user, "birth_date", None) or user_data.get("birth_date", None),
            },
            **tokens,
        }

    def handle_callback(self, request):
        code = request.GET.get("code")
        code_verifier = request.GET.get("code_verifier")
        if hasattr(request, "data") and isinstance(request.data, dict):
            if not code:
                code = request.data.get("code")
            if not code_verifier:
                code_verifier = request.data.get("code_verifier")

        if not code:
            return Response(
                {"error": "Avtorizatsiya kodi ('code') topilmadi."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        client = get_passport_client()

        try:
            user_data = client.authenticate_code(code, code_verifier=code_verifier)
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
        signature = request.headers.get("X-SSO-Signature") or request.META.get("HTTP_X_SSO_SIGNATURE")
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
        token = request.data.get("access_token") if hasattr(request, "data") and isinstance(request.data, dict) else None
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
            "passport_id": user_data.get("passport_id") or getattr(user, "passport_id", None),
            "username": getattr(user, "username", ""),
            "full_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
            "email": getattr(user, "email", ""),
            "phone": getattr(user, "phone_number", None) or getattr(user, "phone", None) or user_data.get("phone", ""),
            "avatar": getattr(user, "avatar", None) or user_data.get("avatar", ""),
            "birth_date": getattr(user, "birth_date", None) or user_data.get("birth_date", None),
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

        payload_user = request.data.get("user") if hasattr(request, "data") and isinstance(request.data, dict) else None
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
