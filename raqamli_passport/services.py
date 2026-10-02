from typing import Tuple, List, Dict, Any, Optional

try:
    from django.conf import settings
except ImportError:
    settings = None

from .client import PassportClient
from .exceptions import PassportSDKError


def get_passport_client() -> PassportClient:
    """PassportClient instansiyasini Django settings sozlamalari asosida qaytaradi."""
    if settings is None:
        raise PassportSDKError("Django o'rnatilmagan yoki sozlanmagan.")
    backend_url = getattr(settings, "PASSPORT_BACKEND_URL", "")
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


def populate_user_fields(user, user_data: dict) -> List[str]:
    """
    Passport-dan kelgan ma'lumotlarni User obyektiga moslab to'ldiradi.
    Viloyat (region) va tuman (district) ID-lar loyihalarda har xil bo'lgani sababli
    avtomatik bog'lanmaydi.

    User modelida mavjud bo'lgan barcha mos maydonlar avtomatik to'ldiriladi:
    - first_name, last_name, email
    - phone / phone_number
    - avatar
    - birth_date
    - passport_id
    """
    updated_fields = []

    passport_id = user_data.get("passport_id") or user_data.get("id")
    if (
        passport_id
        and hasattr(user, "passport_id")
        and getattr(user, "passport_id") != passport_id
    ):
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
    if (
        birth_date
        and hasattr(user, "birth_date")
        and getattr(user, "birth_date") != birth_date
    ):
        user.birth_date = birth_date
        updated_fields.append("birth_date")

    return updated_fields


def find_or_create_user(user_model, user_data: dict) -> Tuple[Any, bool]:
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
        user.username = (
            f"passport_{passport_id}"
            if passport_id
            else (user_data.get("username") or phone or email)
        )

    populate_user_fields(user, user_data)
    if hasattr(user, "set_unusable_password"):
        user.set_unusable_password()

    user.save()
    return user, created


def generate_user_jwt_tokens(user) -> Dict[str, str]:
    """
    Agar simplejwt o'rnatilgan bo'lsa, user uchun access va refresh tokenlarni generatsiya qiladi.
    """
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
    return tokens


class PassportService:
    """
    Passport SSO uchun servis sinfi.
    Biznes logikasini bitta joyda jamlaydi.
    """

    @staticmethod
    def get_client() -> PassportClient:
        return get_passport_client()

    @staticmethod
    def populate_user(user, user_data: dict) -> List[str]:
        return populate_user_fields(user, user_data)

    @staticmethod
    def get_or_create_user(user_model, user_data: dict) -> Tuple[Any, bool]:
        return find_or_create_user(user_model, user_data)

    @staticmethod
    def generate_tokens(user) -> Dict[str, str]:
        return generate_user_jwt_tokens(user)
