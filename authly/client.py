import hashlib
import hmac
import requests
from urllib.parse import urlencode
from typing import Dict, Any, Optional, Tuple
from .exceptions import (
    AuthlySDKError,
    AuthlyTokenExchangeError,
    AuthlyProfileFetchError,
    AuthlyWebhookSignatureError,
)


def calculate_signature(secret: str, payload_bytes: bytes) -> str:
    """HMAC-SHA256 yordamida payload imzosini hisoblaydi."""
    digest = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return f"sha256={digest}"


def verify_webhook_signature(secret: str, payload_bytes: bytes, signature: str) -> bool:
    """Webhook so'rovidan kelgan imzoni tekshiradi."""
    if not secret or not signature:
        return False
    expected = calculate_signature(secret, payload_bytes)
    return hmac.compare_digest(expected, signature)


class AuthlyClient:
    """
    Authly SSO (OAuth2) bilan aloqa o'rnatuvchi mijoz klassi.
    Sof Python, FastAPI, Flask yoki Django loyihalarida to'g'ridan-to'g'ri ishlatilishi mumkin.
    """

    def __init__(
        self,
        backend_url: Optional[str] = None,
        frontend_url: Optional[str] = None,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
        timeout: int = 10,
        webhook_secret: Optional[str] = None,
    ):
        clean_backend = (backend_url or "").rstrip("/")
        clean_frontend = (frontend_url or clean_backend).rstrip("/")

        self.backend_url = clean_backend
        self.frontend_url = clean_frontend
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.timeout = timeout
        self.webhook_secret = webhook_secret

    def get_authorization_url(
        self,
        scope: str = "read",
        state: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ) -> str:
        """Foydalanuvchini Authly SSO login sahifasiga yo'naltiruvchi havola yasaydi."""
        target_redirect_uri = redirect_uri or self.redirect_uri
        if not target_redirect_uri:
            raise AuthlySDKError(
                "'redirect_uri' ko'rsatilmadi. Metodga 'redirect_uri' uzating yoki sozlamalarda 'redirect_uri' ni belgilang."
            )
        params = {
            "client_id": self.client_id,
            "redirect_uri": target_redirect_uri,
            "scope": scope,
        }
        if state:
            params["state"] = state
        return f"{self.frontend_url}/login?{urlencode(params)}"

    def exchange_code_for_token(
        self,
        code: str,
        code_verifier: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bir martalik avtorizatsiya kodini OAuth tokenlarga almashtiradi."""
        target_redirect_uri = redirect_uri or self.redirect_uri
        if not target_redirect_uri:
            raise AuthlyTokenExchangeError(
                "'redirect_uri' ko'rsatilmadi. Metodga 'redirect_uri' uzating yoki sozlamalarda 'redirect_uri' ni belgilang."
            )
        token_endpoint = f"{self.backend_url}/oauth/token/"
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": target_redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Authly-Python-SDK/0.4.0",
        }

        try:
            response = requests.post(
                token_endpoint, data=payload, headers=headers, timeout=self.timeout
            )
            if response.status_code != 200:
                raise AuthlyTokenExchangeError(
                    message="Token olishda xatolik yuz berdi",
                    status_code=response.status_code,
                    details=response.text,
                )
            return response.json()
        except requests.RequestException as e:
            raise AuthlyTokenExchangeError(
                f"Authly serveriga bog'lanishda xatolik: {str(e)}"
            )

    def get_user_profile(self, access_token: str) -> Dict[str, Any]:
        """OAuth access_token orqali foydalanuvchi ma'lumotlarini yuklaydi."""
        profile_endpoint = f"{self.backend_url}/api/v1/sso/profile/"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "Authly-Python-SDK/0.4.0",
        }

        try:
            response = requests.get(
                profile_endpoint, headers=headers, timeout=self.timeout
            )
            if response.status_code != 200:
                raise AuthlyProfileFetchError(
                    message="Profil ma'lumotlarini olish imkoni bo'lmadi",
                    status_code=response.status_code,
                    details=response.text,
                )
            data = response.json()
            if isinstance(data, dict):
                if "data" in data and isinstance(data["data"], dict):
                    return data["data"]
                if "user" in data and isinstance(data["user"], dict):
                    return data["user"]
            return data
        except requests.RequestException as e:
            raise AuthlyProfileFetchError(
                f"Authly serveriga bog'lanishda xatolik: {str(e)}"
            )

    def authenticate_code(
        self,
        code: str,
        code_verifier: Optional[str] = None,
        redirect_uri: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], str]:
        """
        Kodni berib, foydalanuvchi profili va Authly access_token ni qaytaruvchi metod.
        Qaytaradi: (profile_dict, access_token_str)
        """
        token_data = self.exchange_code_for_token(
            code, code_verifier=code_verifier, redirect_uri=redirect_uri
        )
        access_token = token_data.get("access_token")
        profile = self.get_user_profile(access_token)
        return profile, access_token

    def verify_webhook_signature(
        self, payload_bytes: bytes, signature: str, secret: Optional[str] = None
    ) -> bool:
        """Kelgan webhook so'rovining imzosini tekshiradi."""
        target_secret = secret or self.webhook_secret
        return verify_webhook_signature(target_secret, payload_bytes, signature)


