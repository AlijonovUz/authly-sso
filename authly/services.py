import logging
import os
from typing import Tuple, List, Dict, Any, Optional
from urllib.parse import urlparse

import requests

try:
    from django.conf import settings
except ImportError:
    settings = None

from .client import AuthlyClient
from .exceptions import AuthlySDKError

logger = logging.getLogger(__name__)


def get_authly_client() -> AuthlyClient:
    """AuthlyClient instansiyasini Django sozlamalari asosida qaytaradi."""
    if settings is None:
        raise AuthlySDKError("Django o'rnatilmagan yoki sozlanmagan.")

    backend_url = getattr(settings, "AUTHLY_BACKEND_URL", "")
    frontend_url = getattr(settings, "AUTHLY_FRONTEND_URL", None) or backend_url
    client_id = getattr(settings, "AUTHLY_CLIENT_ID", "")
    client_secret = getattr(settings, "AUTHLY_CLIENT_SECRET", "")
    redirect_uri = getattr(settings, "AUTHLY_REDIRECT_URI", "")
    timeout = getattr(settings, "AUTHLY_TIMEOUT", 10)
    webhook_secret = getattr(settings, "AUTHLY_WEBHOOK_SECRET", None)

    return AuthlyClient(
        backend_url=backend_url,
        frontend_url=frontend_url,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        timeout=timeout,
        webhook_secret=webhook_secret,
    )


def extract_user_payload(data: dict) -> dict:
    """Authly API yoki webhook payload ichidan user ma'lumotlarini ajratib oladi."""
    if not isinstance(data, dict):
        return {}
    if "data" in data and isinstance(data["data"], dict):
        return data["data"]
    if "user" in data and isinstance(data["user"], dict):
        return data["user"]
    return data


def populate_user_fields(user, user_data: dict) -> List[str]:
    """
    Authly SSO dan kelgan ma'lumotlarni User obyektiga moslab to'ldiradi.
    Lokal modelda mavjud bo'lgan barcha mos maydonlar avtomatik to'ldiriladi:
    - authly_id
    - first_name, last_name, email
    - phone / phone_number
    - avatar
    - birth_date
    """
    clean_data = extract_user_payload(user_data)
    updated_fields = []

    raw_authly_id = clean_data.get("authly_id") or clean_data.get("id")
    authly_id = (
        str(raw_authly_id).strip()
        if raw_authly_id and str(raw_authly_id).strip()
        else None
    )

    if authly_id and hasattr(user, "authly_id") and getattr(user, "authly_id") != authly_id:
        user.authly_id = authly_id
        updated_fields.append("authly_id")

    first_name = (clean_data.get("first_name") or "").strip()
    if (
        first_name
        and hasattr(user, "first_name")
        and getattr(user, "first_name") != first_name
    ):
        user.first_name = first_name
        updated_fields.append("first_name")

    last_name = (clean_data.get("last_name") or "").strip()
    if (
        last_name
        and hasattr(user, "last_name")
        and getattr(user, "last_name") != last_name
    ):
        user.last_name = last_name
        updated_fields.append("last_name")

    raw_email = clean_data.get("email")
    email = (
        raw_email.strip()
        if isinstance(raw_email, str) and raw_email.strip()
        else None
    )
    if email and hasattr(user, "email") and getattr(user, "email") != email:
        user.email = email
        updated_fields.append("email")

    raw_phone = clean_data.get("phone") or clean_data.get("phone_number")
    phone = (
        str(raw_phone).strip() if raw_phone and str(raw_phone).strip() else None
    )
    if phone:
        if hasattr(user, "phone_number") and getattr(user, "phone_number") != phone:
            user.phone_number = phone
            updated_fields.append("phone_number")
        elif hasattr(user, "phone") and getattr(user, "phone") != phone:
            user.phone = phone
            updated_fields.append("phone")

    avatar = (
        clean_data.get("avatar")
        or clean_data.get("image")
        or clean_data.get("photo")
        or ""
    )
    avatar_field_name = None
    for fname in ["avatar", "image", "photo", "profile_image", "profile_photo"]:
        if hasattr(user, fname):
            avatar_field_name = fname
            break

    if avatar and avatar_field_name:
        is_file_field = False
        try:
            from django.db.models import FileField

            field = user._meta.get_field(avatar_field_name)
            is_file_field = isinstance(field, FileField)
        except Exception:
            pass

        if is_file_field:
            avatar_url = avatar.strip() if isinstance(avatar, str) else ""
            if avatar_url and not (
                avatar_url.startswith("http://") or avatar_url.startswith("https://")
            ):
                base_url = getattr(settings, "AUTHLY_BACKEND_URL", "")
                if not base_url:
                    try:
                        client = get_authly_client()
                        base_url = client.base_url
                    except Exception:
                        base_url = "https://api.authly.uz"
                avatar_url = f"{base_url.rstrip('/')}/{avatar_url.lstrip('/')}"

            if avatar_url and (
                avatar_url.startswith("http://") or avatar_url.startswith("https://")
            ):
                try:
                    res = requests.get(avatar_url, timeout=5)
                    if res.status_code == 200:
                        from django.core.files.base import ContentFile

                        path = urlparse(avatar_url).path
                        ext = os.path.splitext(path)[1] or ".jpg"
                        filename = f"authly_{authly_id or user.pk or 'avatar'}{ext}"
                        getattr(user, avatar_field_name).save(
                            filename, ContentFile(res.content), save=False
                        )
                        updated_fields.append(avatar_field_name)
                except Exception as exc:
                    logger.warning("Avatar yuklab olishda xatolik yuz berdi: %s", exc)
        else:
            if getattr(user, avatar_field_name) != avatar:
                setattr(user, avatar_field_name, avatar)
                updated_fields.append(avatar_field_name)

    birth_date = clean_data.get("birth_date")
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
    Authly ma'lumotlari orqali foydalanuvchini topadi yoki yangi yaratadi.
    Qidirish tartibi:
    1. authly_id
    2. username ("authly_{authly_id}")
    3. phone / phone_number
    4. email
    """
    clean_data = extract_user_payload(user_data)
    raw_authly_id = clean_data.get("authly_id") or clean_data.get("id")
    authly_id = (
        str(raw_authly_id).strip()
        if raw_authly_id and str(raw_authly_id).strip()
        else None
    )
    user = None

    if authly_id and hasattr(user_model, "authly_id"):
        user = user_model.objects.filter(authly_id=authly_id).first()

    if not user and authly_id and hasattr(user_model, "username"):
        user = user_model.objects.filter(username=f"authly_{authly_id}").first()

    raw_phone = clean_data.get("phone") or clean_data.get("phone_number")
    phone = (
        str(raw_phone).strip() if raw_phone and str(raw_phone).strip() else None
    )
    if not user and phone:
        if hasattr(user_model, "phone_number"):
            user = user_model.objects.filter(phone_number=phone).first()
        elif hasattr(user_model, "phone"):
            user = user_model.objects.filter(phone=phone).first()

    raw_email = clean_data.get("email")
    email = (
        raw_email.strip()
        if isinstance(raw_email, str) and raw_email.strip()
        else None
    )
    if not user and email and hasattr(user_model, "email"):
        user = user_model.objects.filter(email=email).first()

    if user:
        created = False
        updated = populate_user_fields(user, clean_data)
        if updated:
            user.save()
        return user, created

    created = True
    user = user_model()
    if hasattr(user, "username"):
        user.username = (
            f"authly_{authly_id}"
            if authly_id
            else (clean_data.get("username") or phone or email)
        )

    populate_user_fields(user, clean_data)
    if hasattr(user, "set_unusable_password"):
        user.set_unusable_password()

    user.save()
    return user, created


def generate_user_jwt_tokens(user) -> Dict[str, str]:
    """
    Agar rest_framework_simplejwt o'rnatilgan bo'lsa,
    user uchun access va refresh tokenlarni generatsiya qiladi.
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


class AuthlyService:
    """
    Authly SSO uchun servis klassi.
    Biznes mantiqini bitta joyda jamlaydi.
    """

    @staticmethod
    def get_client() -> AuthlyClient:
        return get_authly_client()

    @staticmethod
    def populate_user(user, user_data: dict) -> List[str]:
        return populate_user_fields(user, user_data)

    @staticmethod
    def get_or_create_user(user_model, user_data: dict) -> Tuple[Any, bool]:
        return find_or_create_user(user_model, user_data)

    @staticmethod
    def generate_tokens(user) -> Dict[str, str]:
        return generate_user_jwt_tokens(user)
