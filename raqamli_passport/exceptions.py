class PassportSDKError(Exception):
    """Asosiy SDK xatoligi."""
    pass


class PassportTokenExchangeError(PassportSDKError):
    """Kodni tokenga almashtirishda xatolik yuz berganda."""
    def __init__(self, message, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class PassportProfileFetchError(PassportSDKError):
    """Foydalanuvchi profilini olishda xatolik yuz berganda."""
    def __init__(self, message, status_code=None, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class PassportWebhookSignatureError(PassportSDKError):
    """Webhook imzosini tekshirishda xatolik yuz berganda."""
    pass