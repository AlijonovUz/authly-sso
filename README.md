# 🛡️ Authly SSO

Loyiha va xizmatlar uchun yagona **Authly SSO (Single Sign-On / OAuth 2.0)** integratsiya kutubxonasi.

[![PyPI version](https://badge.fury.io/py/authly-sso.svg)](https://badge.fury.io/py/authly-sso)
[![Python](https://img.shields.io/pypi/pyversions/authly-sso)](https://pypi.org/project/authly-sso/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Imkoniyatlar

- **Backend va Frontend domenlari ajratilgan**:
  - `AUTHLY_BACKEND_URL` — Token olish, profil yuklash va barcha server-to-server API so'rovlari.
  - `AUTHLY_FRONTEND_URL` — Foydalanuvchini brauzerda SSO login sahifasiga yo'naltirish havolasini yasash.
- **Django & DRF tayyor integratsiyasi** — 4 ta tayyor endpoint:
  - `login-url/` — Authly SSO ga yo'naltiruvchi login havolasini olish.
  - `callback/` — OAuth2 code orqali tizimga kirish va tokenlar qaytarish.
  - `webhook/` — Authly SSO dan avtomatik foydalanuvchi ma'lumotlarini yangilash.
  - `sync/` — Foydalanuvchi profilini qo'lda Authly bilan sinxronlashtirish.
- **Dinamik `redirect_uri`** — Har bir so'rovda `redirect_uri` ni so'rov orqali uzatish mumkin (settings.py da ham belgilash mumkin).
- **To'liq ma'lumotlar sinxronizatsiyasi** — `authly_id`, `first_name`, `last_name`, `email`, `phone`/`phone_number`, `avatar`, `birth_date` avtomatik to'ldiriladi.
- **HMAC SHA-256 Webhook xavfsizligi** — `X-SSO-Signature` imzosini avtomatik tekshirish.
- **Avtomatik JWT** — `djangorestframework-simplejwt` mavjud bo'lsa `access` va `refresh` tokenlar generatsiya qilinadi.
- **500 xatoliksiz** — Barcha xatoliklar (`AuthlySDKError`, `IntegrityError`, `DatabaseError`, `PermissionDenied` va h.k.) DRF `Response` sifatida qaytariladi.

---

## 📦 O'rnatish

```bash
# Faqat Python (FastAPI, Flask, skriptlar uchun):
pip install authly-sso

# Django / DRF bilan:
pip install "authly-sso[django]"
```

---

## ⚙️ Sozlash

`settings.py` ga quyidagilarni qo'shing:

```python
AUTHLY_BACKEND_URL  = "https://api.authly.uz"
AUTHLY_FRONTEND_URL = "https://authly.uz"
AUTHLY_CLIENT_ID    = "sizning-client-id"
AUTHLY_CLIENT_SECRET = "sizning-client-secret"

# Ixtiyoriy — frontend har so'rovda dinamik yuborsa kerak emas:
AUTHLY_REDIRECT_URI = "https://saytingiz.uz/api/v1/auth/authly/callback/"

# Webhook xavfsizligi uchun:
AUTHLY_WEBHOOK_SECRET = "sizning-webhook-secret"

# Ixtiyoriy (standart: 10 soniya):
AUTHLY_TIMEOUT = 10
```

---

## 🛠 Django / DRF da ishlatish

### 1. `urls.py` ga uling

```python
from django.urls import path, include

urlpatterns = [
    path("api/v1/auth/authly/", include("authly.urls")),
]
```

4 ta endpoint faollashadi:

| Endpoint | Method | Tavsif |
|----------|--------|--------|
| `login-url/` | `GET` | Authly SSO login havolasini qaytaradi |
| `callback/` | `GET`, `POST` | OAuth2 code → foydalanuvchi & tokenlar |
| `webhook/` | `POST` | Authly dan avtomatik yangilash |
| `sync/` | `GET`, `POST` | Foydalanuvchi profilini qo'lda yangilash |

---

### 2. Login havolasini olish

```http
GET /api/v1/auth/authly/login-url/?redirect_uri=https://saytingiz.uz/callback
```

**Parametrlar (query string):**

| Parametr | Majburiy | Tavsif |
|----------|----------|--------|
| `redirect_uri` | Ha\* | Callback URL. `AUTHLY_REDIRECT_URI` settings da belgilangan bo'lsa ixtiyoriy. |
| `scope` | Yo'q | Ruxsatlar doirasi (standart: `read`) |
| `state` | Yo'q | CSRF himoyasi yoki holat parametri |

**Javob:**
```json
{
  "data": {
    "url": "https://authly.uz/login?client_id=...&redirect_uri=...&scope=read"
  },
  "error": null,
  "success": true
}
```

---

### 3. Callback (tizimga kirish)

```http
GET /api/v1/auth/authly/callback/?code=<CODE>&redirect_uri=<URI>
POST /api/v1/auth/authly/callback/
Content-Type: application/json

{"code": "...", "redirect_uri": "..."}
```

**Parametrlar:**

| Parametr | Tavsif |
|----------|--------|
| `code` | Authly SSO dan kelgan bir martalik kod |
| `redirect_uri` | Login havolasi yasashda ishlatilgan xuddi shu URL |
| `code_verifier` | PKCE ishlatilsa (ixtiyoriy) |

**Muvaffaqiyatli javob:**
```json
{
  "data": {
    "is_new_user": false,
    "user": {
      "id": 1,
      "authly_id": "c1f7a0b3-1234-4567-89ab-cdef01234567",
      "username": "authly_c1f7a0b3-1234-4567-89ab-cdef01234567",
      "full_name": "Ism Familiya",
      "first_name": "Ism",
      "last_name": "Familiya",
      "email": "user@example.com",
      "phone": "+998901234567",
      "avatar": "https://api.authly.uz/media/users/avatar/2026/10/avatar.jpg",
      "birth_date": "1995-05-15"
    },
    "access": "<LOCAL_JWT_ACCESS_TOKEN>",
    "refresh": "<LOCAL_JWT_REFRESH_TOKEN>",
    "authly_access_token": "<AUTHLY_OAUTH_ACCESS_TOKEN>"
  },
  "error": null,
  "success": true
}
```

> **Muhim:** `authly_access_token` — bu Authly serveriga murojaat qilish uchun OAuth tokeni.
> `access` va `refresh` esa loyihangiz (lokal) JWT tokenlari.
> Frontend `authly_access_token` ni saqlashi va `/sync/` endpointiga shu tokenni yuborishi mumkin.

---

### 4. Profil sinxronizatsiyasi (Manual Sync)

Foydalanuvchi Authly portalida o'z ma'lumotlarini o'zgartirib qaytganda profilini yangilash:

```http
POST /api/v1/auth/authly/sync/
Authorization: Bearer <LOCAL_JWT>
Content-Type: application/json

{"access_token": "<AUTHLY_OAUTH_ACCESS_TOKEN>"}
```

> ⚠️ `access_token` sifatida lokal JWT emas, callback da kelgan **`authly_access_token`** yuboriladi.

**Muvaffaqiyatli javob:**
```json
{
  "data": {
    "status": "success",
    "updated_fields": ["first_name", "avatar"],
    "user": {
      "id": 1,
      "authly_id": "c1f7a0b3-...",
      "first_name": "Yangi Ism",
      "last_name": "Familiya",
      "email": "user@example.com",
      "phone": "+998901234567",
      "avatar": "https://api.authly.uz/media/users/avatar/2026/10/new_avatar.jpg",
      "birth_date": "1995-05-15",
      "region_info": { "id": "...", "name": "Toshkent shahri" },
      "district_info": { "id": "...", "name": "Yunusobod tumani" }
    }
  },
  "error": null,
  "success": true
}
```

---

### 5. Webhook (Avtomatik sinxronizatsiya)

Authly SSO foydalanuvchi ma'lumotlari o'zgarganda webhook yuboradi. SDK:
1. `X-SSO-Signature` (HMAC SHA-256) imzosini tekshiradi.
2. Foydalanuvchini `authly_id` → `phone_number` → `email` ketma-ketligida topadi.
3. Barcha o'zgargan maydonlarni avtomatik yangilaydi.

```http
POST /api/v1/auth/authly/webhook/
X-SSO-Signature: sha256=<HMAC>
Content-Type: application/json

{
  "event": "user.updated",
  "timestamp": "2026-10-31T12:00:00.000Z",
  "user": {
    "id": "c1f7a0b3-...",
    "authly_id": "c1f7a0b3-...",
    "first_name": "Alisher",
    "last_name": "Valiyev",
    "phone": "+998901234567",
    "email": "alisher@example.com",
    "avatar": "https://api.authly.uz/media/users/avatar/2026/10/new_avatar.jpg",
    "birth_date": "1998-05-15",
    "region": { "id": "...", "name": "Toshkent shahri" },
    "district": { "id": "...", "name": "Yunusobod tumani" }
  }
}
```

---

## 🧩 Maxsus moslashtirish (Override)

### Viloyat/Tuman bog'lash va bloklash tekshiruvi

```python
from authly.views import AuthlyCallbackAPIView, AuthlyWebhookAPIView
from rest_framework.exceptions import PermissionDenied
from apps.users.models import Region, District

class CustomAuthlyCallbackView(AuthlyCallbackAPIView):
    def get_or_create_user(self, user_data: dict):
        user, created = super().get_or_create_user(user_data)

        region_data = user_data.get("region_info") or user_data.get("region")
        district_data = user_data.get("district_info") or user_data.get("district")

        if region_data and hasattr(user, "region"):
            user.region = Region.objects.filter(
                name__iexact=region_data.get("name")
            ).first()
        if district_data and hasattr(user, "district"):
            user.district = District.objects.filter(
                name__iexact=district_data.get("name")
            ).first()

        user.save()

        if getattr(user, "is_blocked", False):
            raise PermissionDenied("Hisobingiz administrator tomonidan bloklangan.")

        return user, created


class CustomAuthlyWebhookView(AuthlyWebhookAPIView):
    def sync_user(self, user_data: dict):
        user = super().sync_user(user_data)
        # Qo'shimcha logika...
        return user
```

### Javob formatini o'zgartirish

```python
class CustomAuthlyCallbackView(AuthlyCallbackAPIView):
    def get_response_data(self, user, user_data, created, tokens, authly_access_token=None):
        data = super().get_response_data(user, user_data, created, tokens, authly_access_token)
        data["my_custom_field"] = "qiymat"
        return data
```

---

## 🐍 Sof Python / FastAPI / Flask da ishlatish

```python
from authly import AuthlyClient, AuthlySDKError

client = AuthlyClient(
    backend_url="https://api.authly.uz",
    frontend_url="https://authly.uz",
    client_id="sizning-client-id",
    client_secret="sizning-client-secret",
    redirect_uri="https://saytingiz.uz/callback",
    webhook_secret="sizning-webhook-secret",
)

# 1. Login havolasi:
url = client.get_authorization_url(scope="read", state="csrf_token")

# 2. Code → profil + authly access_token:
try:
    profile, authly_access_token = client.authenticate_code(
        code="authorization_code_here",
        redirect_uri="https://saytingiz.uz/callback",
    )
    print(profile)              # {"authly_id": "...", "first_name": "...", ...}
    print(authly_access_token)  # "eyJ..." — Authly OAuth tokeni
except AuthlySDKError as e:
    print(f"Xatolik: {e}")

# 3. access_token bilan profil olish:
profile = client.get_user_profile(access_token=authly_access_token)

# 4. Webhook imzosini tekshirish:
is_valid = client.verify_webhook_signature(
    payload_bytes=raw_body,
    signature=request.headers.get("X-SSO-Signature"),
)
```

---

## ⚠️ Xatoliklar (Exceptions)

| Sinf | Sababi |
|------|--------|
| `AuthlySDKError` | Barcha SDK xatoliklari uchun asosiy sinf |
| `AuthlyTokenExchangeError` | Kodni tokenga almashtirishdagi xatolik |
| `AuthlyProfileFetchError` | Profil olishdagi xatolik |
| `AuthlyWebhookSignatureError` | Webhook imzosi xatoligi |

---

## 📋 Jarayon diagrammasi

```
Frontend                Backend (SDK)           Authly Server
   |                        |                       |
   |-- GET /login-url/ ---> |                       |
   |                        |-- get_authorization_url()
   |<-- {"url": "https://authly.uz/login?..."} ----|
   |                        |                       |
   |-- redirect to Authly login page -------------> |
   |<-- redirect back with ?code=<CODE> ----------- |
   |                        |                       |
   |-- POST /callback/ ---> |                       |
   |   {code, redirect_uri} |-- exchange_code_for_token() --> Authly
   |                        |<-- {access_token, ...} <------- Authly
   |                        |-- get_user_profile(access_token) -> Authly
   |                        |<-- {authly_id, phone, ...} <--- Authly
   |                        |-- find_or_create_user()
   |                        |-- generate_jwt_tokens()
   |<-- {user, access, refresh, authly_access_token}
```

---

## 📄 Litsenziya

MIT litsenziyasi ostida tarqatiladi.
Savollar va takliflar uchun **Authly** jamoasiga murojaat qiling.
