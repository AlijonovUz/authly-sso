import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .client import verify_webhook_signature
from .exceptions import AuthlySDKError
from .services import (
    AuthlyService,
    extract_user_payload,
    find_or_create_user,
    generate_user_jwt_tokens,
    get_authly_client,
    populate_user_fields,
)

logger = logging.getLogger(__name__)

User = get_user_model()


def _error(detail: str, details: dict = None, http_status: int = 400) -> Response:
    """Xatolik uchun standart DRF Response qaytaradi."""
    payload = {"detail": detail}
    if details:
        if isinstance(details, dict):
            payload.update(details)
        else:
            payload["info"] = str(details)
    return Response(payload, status=http_status)


def _get_avatar_url(user, clean_data: dict) -> str:
    """Foydalanuvchi avatarining xavfsiz URL matnini qaytaradi (JSON seriyalizatsiya uchun)."""
    avatar_val = None
    for field_name in ("avatar", "image", "photo", "profile_image", "profile_photo"):
        if hasattr(user, field_name):
            field_obj = getattr(user, field_name, None)
            if field_obj:
                try:
                    avatar_val = field_obj.url
                except Exception:
                    avatar_val = str(field_obj)
                if avatar_val:
                    break
    if not avatar_val:
        avatar_val = (
            clean_data.get("avatar")
            or clean_data.get("image")
            or clean_data.get("photo")
            or ""
        )
    return str(avatar_val) if avatar_val else ""


class AuthlyAuthorizeURLAPIView(APIView):
    """
    Frontend uchun Authly SSO login havolasini generatsiya qilib beruvchi endpoint.
    Ixtiyoriy parametrlar: scope, state, redirect_uri.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """GET so'rovi orqali OAuth2 avtorizatsiya URL-ini qaytaradi."""
        try:
            client = get_authly_client()
        except AuthlySDKError as exc:
            logger.error("AuthlyClient yaratishda xatolik: %s", exc)
            return _error(str(exc), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.exception("Kutilmagan xatolik AuthlyClient yaratishda")
            return _error(
                "Authly konfiguratsiyasida ichki xatolik yuz berdi.",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        scope = request.GET.get("scope", "read")
        state = request.GET.get("state")
        redirect_uri = request.GET.get("redirect_uri")
        final_redirect_uri = redirect_uri or client.redirect_uri

        if not final_redirect_uri:
            return _error(
                "'redirect_uri' ko'rsatilmadi. So'rovda 'redirect_uri' parametrini "
                "yuboring yoki loyiha sozlamalarida AUTHLY_REDIRECT_URI ni belgilang.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            url = client.get_authorization_url(
                scope=scope, state=state, redirect_uri=final_redirect_uri
            )
            return Response({"url": url}, status=status.HTTP_200_OK)
        except AuthlySDKError as exc:
            return _error(str(exc), http_status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Avtorizatsiya URL yaratishda kutilmagan xatolik")
            return _error(
                "Avtorizatsiya URL yaratishda ichki xatolik yuz berdi.",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AuthlyCallbackAPIView(APIView):
    """
    OAuth2 callback uchun tayyor endpoint.
    Frontend yoki SSO provayderidan kelgan 'code' orqali foydalanuvchini tizimga kiritadi.
    Lokal loyihalar get_or_create_user() va get_response_data() ni override qilishi mumkin.
    """

    permission_classes = [AllowAny]

    def get_user_model(self):
        """Lokal loyiha User modelini qaytaradi."""
        return get_user_model()

    def get_or_create_user(self, user_data: dict):
        """
        Lokal loyiha o'ziga moslab override qilishi uchun asosiy nuqta.
        user_data — Authly'dan kelgan to'liq payload.
        """
        return find_or_create_user(self.get_user_model(), user_data)

    def get_response_data(
        self,
        user,
        user_data: dict,
        created: bool,
        tokens: dict,
        authly_access_token: str = None,
    ) -> dict:
        """
        Muvaffaqiyatli callback uchun javob strukturasini qaytaradi.
        authly_access_token — frontend sinxronizatsiya uchun saqlashi kerak bo'lgan
        Authly OAuth tokeni.
        """
        clean_data = extract_user_payload(user_data)
        raw_authly_id = clean_data.get("authly_id") or clean_data.get("id")
        authly_id = (
            str(raw_authly_id).strip()
            if raw_authly_id and str(raw_authly_id).strip()
            else None
        )

        data = {
            "is_new_user": created,
            "user": {
                "id": user.id,
                "authly_id": authly_id,
                "username": getattr(user, "username", ""),
                "full_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
                "first_name": getattr(user, "first_name", ""),
                "last_name": getattr(user, "last_name", ""),
                "email": getattr(user, "email", ""),
                "phone": (
                    getattr(user, "phone_number", None)
                    or getattr(user, "phone", None)
                    or clean_data.get("phone", "")
                ),
                "avatar": _get_avatar_url(user, clean_data),
                "birth_date": (
                    getattr(user, "birth_date", None)
                    or clean_data.get("birth_date", None)
                ),
            },
            **tokens,
        }
        if authly_access_token:
            data["authly_access_token"] = authly_access_token
        return data

    def generate_tokens(self, user) -> dict:
        """Foydalanuvchi uchun JWT tokenlarini generatsiya qiladi."""
        return generate_user_jwt_tokens(user)

    def handle_callback(self, request):
        """
        Callback so'rovini qayta ishlaydi: code tekshiradi, token almashtiradi,
        user yaratadi yoki topadi, JWT qaytaradi.
        """
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
            return _error(
                "Avtorizatsiya kodi ('code') topilmadi.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            client = get_authly_client()
        except AuthlySDKError as exc:
            logger.error("AuthlyClient yaratishda xatolik: %s", exc)
            return _error(str(exc), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.exception("Authly konfiguratsiyasida kutilmagan xatolik")
            return _error(
                "Authly konfiguratsiyasida ichki xatolik yuz berdi.",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        final_redirect_uri = redirect_uri or client.redirect_uri

        if not final_redirect_uri:
            return _error(
                "'redirect_uri' ko'rsatilmadi. So'rovda 'redirect_uri' parametrini "
                "yuboring yoki loyiha sozlamalarida AUTHLY_REDIRECT_URI ni belgilang.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_data, authly_access_token = client.authenticate_code(
                code, code_verifier=code_verifier, redirect_uri=final_redirect_uri
            )
        except AuthlySDKError as exc:
            return _error(
                str(exc),
                details=getattr(exc, "details", None),
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception("Authly token almashtirishda kutilmagan xatolik")
            return _error(
                "Authly serveri bilan aloqada ichki xatolik yuz berdi.",
                http_status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            user, created = self.get_or_create_user(user_data)
        except APIException:
            raise
        except IntegrityError as exc:
            logger.error("Foydalanuvchi yaratishda IntegrityError: %s", exc)
            return _error(
                "Foydalanuvchi ma'lumotlari saqlashda konflikt yuz berdi. "
                "Iltimos, qaytadan urinib ko'ring.",
                details={"db_error": str(exc)},
                http_status=status.HTTP_409_CONFLICT,
            )
        except DatabaseError as exc:
            logger.error("Foydalanuvchi yaratishda DatabaseError: %s", exc)
            return _error(
                "Foydalanuvchi ma'lumotlari bazaga saqlashda xatolik yuz berdi.",
                details={"db_error": str(exc)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            logger.exception("get_or_create_user da kutilmagan xatolik")
            return _error(
                "Foydalanuvchi yaratishda kutilmagan xatolik yuz berdi.",
                details={"error": str(exc)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            tokens = self.generate_tokens(user)
        except Exception as exc:
            logger.exception("JWT token generatsiyasida xatolik")
            return _error(
                "Token generatsiyasida xatolik yuz berdi.",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            self.get_response_data(
                user, user_data, created, tokens, authly_access_token
            ),
            status=status.HTTP_200_OK,
        )

    def get(self, request, *args, **kwargs):
        """GET orqali callback so'rovini qayta ishlaydi."""
        return self.handle_callback(request)

    def post(self, request, *args, **kwargs):
        """POST orqali callback so'rovini qayta ishlaydi."""
        return self.handle_callback(request)


class AuthlyWebhookAPIView(APIView):
    """
    Authly serveridan avtomatik o'zgarishlarni qabul qiluvchi Webhook endpoint.
    Foydalanuvchi ma'lumotlari o'zgarganda bazadagi foydalanuvchini avtomatik yangilaydi.
    """

    permission_classes = [AllowAny]

    def get_user_model(self):
        """Lokal loyiha User modelini qaytaradi."""
        return get_user_model()

    def get_webhook_secret(self) -> str:
        """Webhook imzosini tekshirish uchun maxfiy kalitni qaytaradi."""
        return getattr(settings, "AUTHLY_WEBHOOK_SECRET", "")

    def verify_signature(self, request) -> bool:
        """X-SSO-Signature sarlavhasi orqali webhook imzosini tekshiradi."""
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
        """Webhook so'rovini qabul qilib foydalanuvchini sinxronlashtiradi."""
        if not self.verify_signature(request):
            return _error(
                "Imzo yaroqsiz yoki mavjud emas.",
                http_status=status.HTTP_401_UNAUTHORIZED,
            )

        payload = request.data if isinstance(request.data, dict) else {}
        user_data = payload.get("user") or payload
        if not user_data or not isinstance(user_data, dict):
            return _error(
                "Foydalanuvchi ma'lumotlari topilmadi.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = self.sync_user(user_data)
        except APIException:
            raise
        except IntegrityError as exc:
            logger.error("Webhook sync IntegrityError: %s", exc)
            return _error(
                "Foydalanuvchi ma'lumotlari saqlashda konflikt yuz berdi.",
                details={"db_error": str(exc)},
                http_status=status.HTTP_409_CONFLICT,
            )
        except DatabaseError as exc:
            logger.error("Webhook sync DatabaseError: %s", exc)
            return _error(
                "Foydalanuvchi bazaga saqlashda xatolik yuz berdi.",
                details={"db_error": str(exc)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as exc:
            logger.exception("Webhook sync_user da kutilmagan xatolik")
            return _error(
                "Sinxronizatsiyada kutilmagan xatolik yuz berdi.",
                details={"error": str(exc)},
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "status": "success",
                "user_id": getattr(user, "id", None),
                "message": "Foydalanuvchi muvaffaqiyatli sinxronlashtirildi.",
            },
            status=status.HTTP_200_OK,
        )


class AuthlySyncProfileAPIView(APIView):
    """
    Foydalanuvchi ma'lumotlarini qo'lda (manual) Authly bilan sinxronlashtirish endpointi.
    Login qilgan foydalanuvchi o'z profilini Authly-dan qayta yangilab olishi mumkin.
    """

    permission_classes = [IsAuthenticated]

    def get_access_token(self, request) -> str:
        """
        So'rovdan yoki sessiyadan Authly OAuth access_token-ni oladi.
        Lokal loyiha tokenni o'z saqlash joyiga qarab override qilishi mumkin.
        """
        token = None
        if hasattr(request, "data") and isinstance(request.data, dict):
            token = request.data.get("access_token") or request.data.get("authly_access_token")
        if not token:
            token = request.GET.get("access_token") or request.GET.get("authly_access_token")
        if not token and hasattr(request, "session"):
            token = request.session.get("authly_access_token")
        return token

    def sync_user(self, user, user_data: dict) -> list:
        """
        Lokal loyiha o'ziga moslab override qilishi uchun asosiy nuqta.
        Foydalanuvchi ma'lumotlarini yangilaydi va o'zgargan maydonlar ro'yxatini qaytaradi.
        """
        updated_fields = populate_user_fields(user, user_data)
        if updated_fields:
            user.save()
        return updated_fields

    def get_response_data(self, user, user_data: dict) -> dict:
        """
        Sinxronizatsiya natijasidagi foydalanuvchi ma'lumotlarini qaytaradi.
        region_info va district_info lokal modeldan olinadi, bo'lmasa Authly
        payloadidagi ma'lumot qaytariladi.
        """
        clean_data = extract_user_payload(user_data)
        raw_authly_id = (
            clean_data.get("authly_id")
            or clean_data.get("id")
            or getattr(user, "authly_id", None)
        )

        region = getattr(user, "region", None)
        if region is not None:
            region_info = {
                "id": getattr(region, "id", None),
                "name": getattr(region, "name", None),
            }
        else:
            region_info = clean_data.get("region_info") or clean_data.get("region")

        district = getattr(user, "district", None)
        if district is not None:
            district_info = {
                "id": getattr(district, "id", None),
                "name": getattr(district, "name", None),
            }
        else:
            district_info = clean_data.get("district_info") or clean_data.get("district")

        return {
            "id": user.id,
            "authly_id": raw_authly_id,
            "first_name": getattr(user, "first_name", ""),
            "last_name": getattr(user, "last_name", ""),
            "email": getattr(user, "email", ""),
            "phone": (
                getattr(user, "phone_number", None)
                or getattr(user, "phone", None)
                or clean_data.get("phone", "")
            ),
            "avatar": _get_avatar_url(user, clean_data),
            "birth_date": (
                getattr(user, "birth_date", None) or clean_data.get("birth_date", None)
            ),
            "region_info": region_info,
            "district_info": district_info,
        }

    def handle_sync(self, request):
        """
        Sinxronizatsiya so'rovini qayta ishlaydi.
        access_token bo'lsa Authly'dan so'nggi profil olinadi,
        aks holda so'rov tanasidagi 'user' ma'lumotlari ishlatiladi.
        """
        access_token = self.get_access_token(request)

        if access_token:
            try:
                client = get_authly_client()
            except AuthlySDKError as exc:
                logger.error("AuthlyClient yaratishda xatolik: %s", exc)
                return _error(str(exc), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as exc:
                logger.exception("Authly konfiguratsiyasida kutilmagan xatolik")
                return _error(
                    "Authly konfiguratsiyasida ichki xatolik yuz berdi.",
                    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            try:
                user_data = client.get_user_profile(access_token)
            except AuthlySDKError as exc:
                return _error(
                    str(exc),
                    details=getattr(exc, "details", None),
                    http_status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as exc:
                logger.exception("Authly profilini olishda kutilmagan xatolik")
                return _error(
                    "Authly serveridan profil olishda xatolik yuz berdi.",
                    http_status=status.HTTP_502_BAD_GATEWAY,
                )

            try:
                updated_fields = self.sync_user(request.user, user_data)
            except APIException:
                raise
            except IntegrityError as exc:
                logger.error("Profile sync IntegrityError: %s", exc)
                return _error(
                    "Profil saqlashda konflikt yuz berdi.",
                    details={"db_error": str(exc)},
                    http_status=status.HTTP_409_CONFLICT,
                )
            except DatabaseError as exc:
                logger.error("Profile sync DatabaseError: %s", exc)
                return _error(
                    "Profil bazaga saqlashda xatolik yuz berdi.",
                    details={"db_error": str(exc)},
                    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            except Exception as exc:
                logger.exception("sync_user da kutilmagan xatolik")
                return _error(
                    "Profil sinxronizatsiyasida kutilmagan xatolik yuz berdi.",
                    details={"error": str(exc)},
                    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

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
            try:
                updated_fields = self.sync_user(request.user, payload_user)
            except APIException:
                raise
            except IntegrityError as exc:
                logger.error("Profile sync (payload) IntegrityError: %s", exc)
                return _error(
                    "Profil saqlashda konflikt yuz berdi.",
                    details={"db_error": str(exc)},
                    http_status=status.HTTP_409_CONFLICT,
                )
            except DatabaseError as exc:
                logger.error("Profile sync (payload) DatabaseError: %s", exc)
                return _error(
                    "Profil bazaga saqlashda xatolik yuz berdi.",
                    details={"db_error": str(exc)},
                    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )
            except Exception as exc:
                logger.exception("sync_user (payload) da kutilmagan xatolik")
                return _error(
                    "Profil sinxronizatsiyasida kutilmagan xatolik yuz berdi.",
                    details={"error": str(exc)},
                    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            return Response(
                {
                    "status": "success",
                    "updated_fields": updated_fields,
                    "user": self.get_response_data(request.user, payload_user),
                },
                status=status.HTTP_200_OK,
            )

        return _error(
            "Sinxronizatsiya uchun 'access_token' yoki 'user' ma'lumotlari yuborilmadi. "
            "So'rov parametrida 'access_token' yuboring yoki 'get_access_token' metodini override qiling.",
            http_status=status.HTTP_400_BAD_REQUEST,
        )

    def get(self, request, *args, **kwargs):
        """GET orqali profil sinxronizatsiyasini amalga oshiradi."""
        return self.handle_sync(request)

    def post(self, request, *args, **kwargs):
        """POST orqali profil sinxronizatsiyasini amalga oshiradi."""
        return self.handle_sync(request)
