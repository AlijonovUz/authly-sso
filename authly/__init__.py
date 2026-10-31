from .client import (
    AuthlyClient,
    calculate_signature,
    verify_webhook_signature,
)
from .exceptions import (
    AuthlySDKError,
    AuthlyTokenExchangeError,
    AuthlyProfileFetchError,
    AuthlyWebhookSignatureError,
)
from .services import (
    AuthlyService,
    get_authly_client,
    populate_user_fields,
    find_or_create_user,
    generate_user_jwt_tokens,
    extract_user_payload,
)

__version__ = "0.4.0"

__all__ = [
    "AuthlyClient",
    "AuthlyService",
    "get_authly_client",
    "populate_user_fields",
    "find_or_create_user",
    "generate_user_jwt_tokens",
    "extract_user_payload",
    "AuthlySDKError",
    "AuthlyTokenExchangeError",
    "AuthlyProfileFetchError",
    "AuthlyWebhookSignatureError",
    "calculate_signature",
    "verify_webhook_signature",
]
