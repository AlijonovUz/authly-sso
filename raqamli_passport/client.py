import hashlib
import hmac
import requests
from urllib.parse import urlencode
from typing import Dict, Any, Optional
from .exceptions import (
    PassportTokenExchangeError,
    PassportProfileFetchError,
    PassportWebhookSignatureError,
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


class PassportClient:
    def __init__(
        self,
        backend_url: Optional[str] = None,
        frontend_url: Optional[str] = None,
        client_id: str = "",
        client_secret: str = "",
        redirect_uri: str = "",
        timeout: int = 10,
        webhook_secret: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        clean_backend = (backend_url or base_url or "").rstrip("/")
        clean_frontend = (frontend_url or clean_backend).rstrip("/")

        self.backend_url = clean_backend
        self.frontend_url = clean_frontend
        self.base_url = clean_backend
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.timeout = timeout
        self.webhook_secret = webhook_secret

    def get_authorization_url(self, scope: str = "read", state: Optional[str] = None) -> str:
        """Foydalanuvchini Passport frontendiga yo'naltiruvchi havola yasaydi."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
        }
        if state:
            params["state"] = state
        return f"{self.frontend_url}/login?{urlencode(params)}"

    def exchange_code_for_token(self, code: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
        """Bir martalik kodni 'access_token'ga almashtiradi."""
        token_endpoint = f"{self.backend_url}/oauth/token/"
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        if code_verifier:
            payload["code_verifier"] = code_verifier

        try:
            response = requests.post(token_endpoint, data=payload, timeout=self.timeout)
            if response.status_code != 200:
                raise PassportTokenExchangeError(
                    message="Token olishda xatolik yuz berdi",
                    status_code=response.status_code,
                    details=response.text,
                )
            return response.json()
        except requests.RequestException as e:
            raise PassportTokenExchangeError(f"Passport serveriga bog'lanishda xatolik: {str(e)}")

    def get_user_profile(self, access_token: str) -> Dict[str, Any]:
        """OAuth access_token orqali foydalanuvchi ma'lumotlarini qaytaradi."""
        profile_endpoint = f"{self.backend_url}/api/v1/sso/profile/"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = requests.get(profile_endpoint, headers=headers, timeout=self.timeout)
            if response.status_code != 200:
                raise PassportProfileFetchError(
                    message="Profil ma'lumotlarini olish imkoni bo'lmadi",
                    status_code=response.status_code,
                    details=response.text,
                )
            return response.json()
        except requests.RequestException as e:
            raise PassportProfileFetchError(f"Passport serveriga bog'lanishda xatolik: {str(e)}")

    def authenticate_code(self, code: str, code_verifier: Optional[str] = None) -> Dict[str, Any]:
        """Kodni berib, darhol oxirgi foydalanuvchi ma'lumotlarini olib beruvchi qulay metod."""
        token_data = self.exchange_code_for_token(code, code_verifier=code_verifier)
        access_token = token_data.get("access_token")
        return self.get_user_profile(access_token)

    def verify_webhook_signature(
        self, payload_bytes: bytes, signature: str, secret: Optional[str] = None
    ) -> bool:
        """Kelgan webhook so'rovining imzosini tekshiradi."""
        target_secret = secret or self.webhook_secret
        return verify_webhook_signature(target_secret, payload_bytes, signature)