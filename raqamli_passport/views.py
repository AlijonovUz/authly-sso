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
from .exceptions import PassportSDKError
from .services import (
    PassportService,
    extract_user_payload,
    find_or_create_user,
    generate_user_jwt_tokens,
    get_passport_client,
    populate_user_fields,
)

logger = logging.getLogger(__name__)

User = get_user_model()


def _error(detail: str, details: dict = None, http_status: int = 400) -> Response:
    """
    Xatolik uchun standart DRF Response qaytaradi.
    ResponseRenderer bu formatni avtomatik ravishda quyidagicha o'raydi:
    {
        "data": null,
        "error": {
            "errorId": <http_status>,
            "errorCode": null,
            "isFriendly": true,
            "errorMsg": "<detail>",
            "details": <details>
        },
        "success": false
    }

    Renderer 'detail' kalitini pop qilib, qolgan dict ni 'details' sifatida ishlatadi.
    Shuning uchun qo'shimcha ma'lumotlar payload ga to'g'ridan to'g'ri merge qilinadi.
    """
    payload = {"detail": detail}
    if details:
        payload.update(details)
    return Response(payload, status=http_status)


class PassportAuthorizeURLAPIView(APIView):
    """
    Frontend uchun Passport SSO login havolasini generatsiya qilib beruvchi endpoint.
    Ixtiyoriy parametrlar: scope, state, redirect_uri.
    """

    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        """GET so'rovi orqali OAuth2 avtorizatsiya URL-ini qaytaradi."""
        try:
            client = get_passport_client()
        except PassportSDKError as exc:
            logger.error("PassportClient yaratishda xatolik: %s", exc)
            return _error(str(exc), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.exception("Kutilmagan xatolik PassportClient yaratishda")
            return _error(
                "Passport konfiguratsiyasida ichki xatolik yuz berdi.",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        scope = request.GET.get("scope", "read")
        state = request.GET.get("state")
        redirect_uri = request.GET.get("redirect_uri")
        final_redirect_uri = redirect_uri or client.redirect_uri

        if not final_redirect_uri:
            return _error(
                "'redirect_uri' ko'rsatilmadi. So'rovda 'redirect_uri' parametrini "
                "yuboring yoki loyiha sozlamalarida PASSPORT_REDIRECT_URI ni belgilang.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            url = client.get_authorization_url(
                scope=scope, state=state, redirect_uri=final_redirect_uri
            )
            return Response({"url": url}, status=status.HTTP_200_OK)
        except PassportSDKError as exc:
            return _error(str(exc), http_status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Avtorizatsiya URL yaratishda kutilmagan xatolik")
            return _error(
                "Avtorizatsiya URL yaratishda ichki xatolik yuz berdi.",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PassportCallbackAPIView(APIView):
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
        user_data — Passport'dan kelgan to'liq payload (extract qilinmagan).
        """
        return find_or_create_user(self.get_user_model(), user_data)

    def get_response_data(
        self, user, user_data: dict, created: bool, tokens: dict
    ) -> dict:
        """Muvaffaqiyatli callback uchun javob strukturasini qaytaradi."""
        clean_data = extract_user_payload(user_data)
        return {
            "is_new_user": created,
            "user": {
                "id": user.id,
                "passport_id": clean_data.get("passport_id") or clean_data.get("id"),
                "username": getattr(user, "username", ""),
                "full_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
                "email": getattr(user, "email", ""),
                "phone": (
                    getattr(user, "phone_number", None)
                    or getattr(user, "phone", None)
                    or clean_data.get("phone", "")
                ),
                "avatar": getattr(user, "avatar", None) or clean_data.get("avatar", ""),
                "birth_date": (
                    getattr(user, "birth_date", None)
                    or clean_data.get("birth_date", None)
                ),
            },
            **tokens,
        }

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
            client = get_passport_client()
        except PassportSDKError as exc:
            logger.error("PassportClient yaratishda xatolik: %s", exc)
            return _error(str(exc), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as exc:
            logger.exception("Passport konfiguratsiyasida kutilmagan xatolik")
            return _error(
                "Passport konfiguratsiyasida ichki xatolik yuz berdi.",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        final_redirect_uri = redirect_uri or client.redirect_uri

        if not final_redirect_uri:
            return _error(
                "'redirect_uri' ko'rsatilmadi. So'rovda 'redirect_uri' parametrini "
                "yuboring yoki loyiha sozlamalarida PASSPORT_REDIRECT_URI ni belgilang.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_data = client.authenticate_code(
                code, code_verifier=code_verifier, redirect_uri=final_redirect_uri
            )
        except PassportSDKError as exc:
            return _error(
                str(exc),
                details=getattr(exc, "details", None),
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as exc:
            logger.exception("Passport token almashtirishda kutilmagan xatolik")
            return _error(
                "Passport serveri bilan aloqada ichki xatolik yuz berdi.",
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
            self.get_response_data(user, user_data, created, tokens),
            status=status.HTTP_200_OK,
        )

    def get(self, request, *args, **kwargs):
        """GET orqali callback so'rovini qayta ishlaydi."""
        return self.handle_callback(request)

    def post(self, request, *args, **kwargs):
        """POST orqali callback so'rovini qayta ishlaydi."""
        return self.handle_callback(request)


class PassportWebhookAPIView(APIView):
    """
    Passport serveridan avtomatik o'zgarishlarni qabul qiluvchi Webhook endpoint.
    Foydalanuvchi ma'lumotlari o'zgarganda bazadagi foydalanuvchini avtomatik yangilaydi.
    """

    permission_classes = [AllowAny]

    def get_user_model(self):
        """Lokal loyiha User modelini qaytaradi."""
        return get_user_model()

    def get_webhook_secret(self) -> str:
        """Webhook imzosini tekshirish uchun maxfiy kalitni qaytaradi."""
        return getattr(settings, "PASSPORT_WEBHOOK_SECRET", "")

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
        Foydalanuvchi ma'lumotlarini yangilaydi va o'zgargan maydonlar ro'yxatini qaytaradi.
        """
        updated_fields = populate_user_fields(user, user_data)
        if updated_fields:
            user.save()
        return updated_fields

    def get_response_data(self, user, user_data: dict) -> dict:
        """Sinxronizatsiya natijasidagi foydalanuvchi ma'lumotlarini qaytaradi."""
        clean_data = extract_user_payload(user_data)
        return {
            "id": user.id,
            "passport_id": clean_data.get("passport_id") or getattr(user, "passport_id", None),
            "username": getattr(user, "username", ""),
            "full_name": f"{getattr(user, 'first_name', '')} {getattr(user, 'last_name', '')}".strip(),
            "email": getattr(user, "email", ""),
            "phone": (
                getattr(user, "phone_number", None)
                or getattr(user, "phone", None)
                or clean_data.get("phone", "")
            ),
            "avatar": getattr(user, "avatar", None) or clean_data.get("avatar", ""),
            "birth_date": (
                getattr(user, "birth_date", None) or clean_data.get("birth_date", None)
            ),
        }

    def handle_sync(self, request):
        """
        Sinxronizatsiya so'rovini qayta ishlaydi.
        access_token bo'lsa Passport'dan so'nggi profil olinadi,
        aks holda so'rov tanasidagi 'user' ma'lumotlari ishlatiladi.
        """
        access_token = self.get_access_token(request)

        if access_token:
            try:
                client = get_passport_client()
            except PassportSDKError as exc:
                logger.error("PassportClient yaratishda xatolik: %s", exc)
                return _error(str(exc), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            except Exception as exc:
                logger.exception("Passport konfiguratsiyasida kutilmagan xatolik")
                return _error(
                    "Passport konfiguratsiyasida ichki xatolik yuz berdi.",
                    http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            try:
                user_data = client.get_user_profile(access_token)
            except PassportSDKError as exc:
                return _error(
                    str(exc),
                    details=getattr(exc, "details", None),
                    http_status=status.HTTP_400_BAD_REQUEST,
                )
            except Exception as exc:
                logger.exception("Passport profilini olishda kutilmagan xatolik")
                return _error(
                    "Passport serveridan profil olishda xatolik yuz berdi.",
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
