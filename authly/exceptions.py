class AuthlySDKError(Exception):
    """Asosiy SDK xatoligi."""

    pass


class AuthlyTokenExchangeError(AuthlySDKError):
    """Kodni tokenga almashtirishda xatolik yuz berganda."""

    def __init__(self, message, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class AuthlyProfileFetchError(AuthlySDKError):
    """Foydalanuvchi profilini olishda xatolik yuz berganda."""

    def __init__(self, message, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class AuthlyWebhookSignatureError(AuthlySDKError):
    """Webhook imzosini tekshirishda xatolik yuz berganda."""

    pass
