import requests
from urllib.parse import urlencode
from typing import Dict, Any
from .exceptions import PassportTokenExchangeError, PassportProfileFetchError


class PassportClient:
    def __init__(
        self,
        base_url: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        timeout: int = 10,
    ):
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.timeout = timeout

    def get_authorization_url(self, scope: str = "read", state: str = None) -> str:
        """Foydalanuvchini Passport frontendiga yo'naltiruvchi havola yasaydi."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
        }
        if state:
            params["state"] = state
        return f"{self.base_url}/login?{urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Bir martalik kodni 'access_token'ga almashtiradi."""
        token_endpoint = f"{self.base_url}/oauth/token/"
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

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
        profile_endpoint = f"{self.base_url}/api/v1/sso/profile/"
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

    def authenticate_code(self, code: str) -> Dict[str, Any]:
        """Kodni berib, darhol oxirgi foydalanuvchi ma'lumotlarini olib beruvchi qulay metod."""
        token_data = self.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        return self.get_user_profile(access_token)