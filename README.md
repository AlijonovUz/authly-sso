# 🛡️ Raqamli Passport SDK

**Raqamli Nazorat LLC** loyihalari uchun yagona SSO (Single Sign-On) Passport integratsiya kutubxonasi.

[![PyPI version](https://badge.fury.io/py/raqamli-passport-sdk.svg)](https://badge.fury.io/py/raqamli-passport-sdk)
[![Python](https://img.shields.io/pypi/pyversions/raqamli-passport-sdk)](https://pypi.org/project/raqamli-passport-sdk/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Imkoniyatlar

- **Backend va Frontend domenlari ajratilgan**:
  - `PASSPORT_BACKEND_URL` — Token olish, profil yuklash va barcha server-to-server API so'rovlari.
  - `PASSPORT_FRONTEND_URL` — Foydalanuvchini brauzerda SSO login sahifasiga yo'naltirish havolasini yasash.
- **Django & DRF tayyor integratsiyasi** — 4 ta tayyor endpoint:
  - `login-url/` — Passport SSO ga yo'naltiruvchi login havolasini olish.
  - `callback/` — OAuth2 code orqali tizimga kirish va tokenlar qaytarish.
  - `webhook/` — Passport SSO dan avtomatik foydalanuvchi ma'lumotlarini yangilash.
  - `sync/` — Foydalanuvchi profilini qo'lda Passport bilan sinxronlashtirish.
- **Dinamik `redirect_uri`** — Har bir so'rovda `redirect_uri` ni so'rov orqali uzatish mumkin (settings.py da ham belgilash mumkin).
- **To'liq ma'lumotlar sinxronizatsiyasi** — `first_name`, `last_name`, `email`, `phone`/`phone_number`, `avatar`, `birth_date`, `passport_id` avtomatik to'ldiriladi.
- **HMAC SHA-256 Webhook xavfsizligi** — `X-SSO-Signature` imzosini avtomatik tekshirish.
- **Avtomatik JWT** — `djangorestframework-simplejwt` mavjud bo'lsa `access` va `refresh` tokenlar generatsiya qilinadi.
- **500 xatoliksiz** — Barcha xatoliklar (`PassportSDKError`, `IntegrityError`, `DatabaseError`, `PermissionDenied` va h.k.) DRF `Response` sifatida qaytariladi.

---

## 📦 O'rnatish

```bash
# Faqat Python (FastAPI, Flask, skriptlar uchun):
pip install raqamli-passport-sdk

# Django / DRF bilan:
pip install "raqamli-passport-sdk[django]"
```

---

## ⚙️ Sozlash

`settings.py` ga quyidagilarni qo'shing:

```python
PASSPORT_BACKEND_URL  = "https://backend-passport.raqamlinazorat.uz"
PASSPORT_FRONTEND_URL = "https://passport.raqamlinazorat.uz"
PASSPORT_CLIENT_ID    = "sizning-client-id"
PASSPORT_CLIENT_SECRET = "sizning-client-secret"

# Ixtiyoriy — frontend har so'rovda dinamik yuborsa kerak emas:
PASSPORT_REDIRECT_URI = "https://myproject.uz/api/v1/auth/passport/callback/"

# Webhook xavfsizligi uchun:
PASSPORT_WEBHOOK_SECRET = "sizning-webhook-secret"

# Ixtiyoriy (standart: 10 soniya):
PASSPORT_TIMEOUT = 10
```

---

## 🛠 Django / DRF da ishlatish

### 1. `urls.py` ga uling

```python
from django.urls import path, include

urlpatterns = [
    path("api/v1/auth/passport/", include("raqamli_passport.urls")),
]
```

4 ta endpoint faollashadi:

| Endpoint | Method | Tavsif |
|----------|--------|--------|
| `login-url/` | `GET` | Passport SSO login havolasini qaytaradi |
| `callback/` | `GET`, `POST` | OAuth2 code → foydalanuvchi & tokenlar |
| `webhook/` | `POST` | Passport dan avtomatik yangilash |
| `sync/` | `GET`, `POST` | Foydalanuvchi profilini qo'lda yangilash |

---

### 2. Login havolasini olish

```
GET /api/v1/auth/passport/login-url/?redirect_uri=https://myapp.uz/callback
```

**Parametrlar (query string):**

| Parametr | Majburiy | Tavsif |
|----------|----------|--------|
| `redirect_uri` | Ha\* | Callback URL. `PASSPORT_REDIRECT_URI` settings da belgilangan bo'lsa ixtiyoriy. |
| `scope` | Yo'q | Ruxsatlar doirasi (standart: `read`) |
| `state` | Yo'q | CSRF himoyasi yoki holat parametri |

**Javob:**
```json
{
  "data": {
    "url": "https://passport.raqamlinazorat.uz/login?client_id=...&redirect_uri=...&scope=read"
  },
  "error": null,
  "success": true
}
```

---

### 3. Callback (tizimga kirish)

```
GET /api/v1/auth/passport/callback/?code=<CODE>&redirect_uri=<URI>
POST /api/v1/auth/passport/callback/
Body: {"code": "...", "redirect_uri": "..."}
```

**Parametrlar:**

| Parametr | Tavsif |
|----------|--------|
| `code` | Passport SSO dan kelgan bir martalik kod |
| `redirect_uri` | Login havolasi yasashda ishlatilgan xuddi shu URL |
| `code_verifier` | PKCE ishlatilsa (ixtiyoriy) |

**Muvaffaqiyatli javob:**
```json
{
  "data": {
    "is_new_user": false,
    "user": {
      "id": 1,
      "passport_id": "uuid-...",
      "username": "passport_uuid",
      "full_name": "Ism Familiya",
      "email": "user@example.com",
      "phone": "+998901234567",
      "avatar": "https://...",
      "birth_date": "1995-05-15"
    },
    "access": "<LOCAL_JWT_ACCESS_TOKEN>",
    "refresh": "<LOCAL_JWT_REFRESH_TOKEN>",
    "passport_access_token": "<PASSPORT_OAUTH_ACCESS_TOKEN>"
  },
  "error": null,
  "success": true
}
```

> **Muhim:** `passport_access_token` — bu Passport serveriga murojaat qilish uchun OAuth tokeni.
> `access` va `refresh` esa loyihangiz (lokal) JWT tokenlari.
> Frontend `passport_access_token` ni xavfsiz joyda saqlashi va `/sync/` endpointiga shu tokenni yuborishi kerak.

---

### 4. Profil sinxronizatsiyasi (Manual Sync)

Foydalanuvchi Passportdagi ma'lumotlarini o'zgartirib qaytganda profilini yangilash:

```
POST /api/v1/auth/passport/sync/
Authorization: Bearer <LOCAL_JWT>
Body: {"access_token": "<PASSPORT_OAUTH_ACCESS_TOKEN>"}
```

> ⚠️ `access_token` sifatida lokal JWT emas, callback da kelgan **`passport_access_token`** yuborilishi shart.

**Muvaffaqiyatli javob:**
```json
{
  "data": {
    "status": "success",
    "updated_fields": ["first_name", "avatar"],
    "user": {
      "id": 1,
      "passport_id": "uuid-...",
      "full_name": "Yangi Ism",
      "email": "user@example.com",
      "phone": "+998901234567",
      "avatar": "https://...",
      "birth_date": "1995-05-15"
    }
  },
  "error": null,
  "success": true
}
```

---

### 5. Webhook (Avtomatik sinxronizatsiya)

Passport SSO foydalanuvchi ma'lumotlari o'zgarganda webhook yuboradi. SDK:
1. `X-SSO-Signature` (HMAC SHA-256) imzosini tekshiradi.
2. Foydalanuvchini `passport_id` → `phone_number` → `email` ketma-ketligida topadi.
3. Barcha o'zgargan maydonlarni avtomatik yangilaydi.

```
POST /api/v1/auth/passport/webhook/
X-SSO-Signature: sha256=<HMAC>
Body: {"user": {"passport_id": "...", "first_name": "...", ...}}
```

---

## 🧩 Maxsus moslashtirish (Override)

### Viloyat/Tuman bog'lash va bloklash tekshiruvi

```python
from raqamli_passport.views import PassportCallbackAPIView, PassportWebhookAPIView
from rest_framework.exceptions import PermissionDenied
from apps.users.models import Region, District

class CustomPassportCallbackView(PassportCallbackAPIView):
    def get_or_create_user(self, user_data: dict):
        user, created = super().get_or_create_user(user_data)

        region_data = user_data.get("region")
        district_data = user_data.get("district")

        if region_data and hasattr(user, "region"):
            user.region = Region.objects.filter(
                name__iexact=region_data.get("name")
            ).first()
        if district_data and hasattr(user, "district"):
            user.district = District.objects.filter(
                name__iexact=district_data.get("name")
            ).first()

        user.save()

        if user.is_blocked:
            raise PermissionDenied("Hisobingiz administrator tomonidan bloklangan.")

        return user, created


class CustomPassportWebhookView(PassportWebhookAPIView):
    def sync_user(self, user_data: dict):
        user = super().sync_user(user_data)
        # Qo'shimcha logika...
        return user
```

> `PermissionDenied` (`rest_framework.exceptions`) ko'tarilsa, SDK uni tutmaydi — DRF o'zi **403** qaytaradi.
> Oddiy `Exception` ko'tarilsa esa SDK **500** sifatida qaytaradi.

### Javob formatini o'zgartirish

```python
class CustomPassportCallbackView(PassportCallbackAPIView):
    def get_response_data(self, user, user_data, created, tokens, passport_access_token=None):
        data = super().get_response_data(user, user_data, created, tokens, passport_access_token)
        data["my_custom_field"] = "qiymat"
        return data
```

### JWT tokensiz ishlash

```python
class CustomPassportCallbackView(PassportCallbackAPIView):
    def generate_tokens(self, user) -> dict:
        return {}
```

---

## 🐍 Sof Python / FastAPI / Flask da ishlatish

```python
from raqamli_passport import PassportClient, PassportSDKError

client = PassportClient(
    backend_url="https://backend-passport.raqamlinazorat.uz",
    frontend_url="https://passport.raqamlinazorat.uz",
    client_id="sizning-client-id",
    client_secret="sizning-client-secret",
    redirect_uri="https://myproject.uz/callback",
    webhook_secret="sizning-webhook-secret",
)

# 1. Login havolasi:
url = client.get_authorization_url(scope="read", state="csrf_token")

# 2. Code → profil + passport access_token:
try:
    profile, passport_access_token = client.authenticate_code(
        code="authorization_code_here",
        redirect_uri="https://myproject.uz/callback",
    )
    print(profile)              # {"passport_id": "...", "first_name": "...", ...}
    print(passport_access_token)  # "eyJ..." — Passport OAuth tokeni
except PassportSDKError as e:
    print(f"Xatolik: {e}")

# 3. access_token bilan profil olish:
profile = client.get_user_profile(access_token=passport_access_token)

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
| `PassportSDKError` | Barcha SDK xatoliklari uchun asosiy sinf |
| `PassportTokenExchangeError` | Kodni tokenga almashtirishdagi xatolik |
| `PassportProfileFetchError` | Profil olishdagi xatolik |
| `PassportWebhookSignatureError` | Webhook imzosi xatoligi |

DRF viewlarda barcha xatoliklar JSON response sifatida qaytariladi — server hech qachon 500 bilan yiqilmaydi.

---

## 📋 Callback jarayon diagrammasi

```
Frontend                Backend (SDK)           Passport SSO
   |                        |                       |
   |-- GET /login-url/ ---> |                       |
   |                        |-- get_authorization_url()
   |<-- {"url": "https://passport.../login?..."} ---|
   |                        |                       |
   |-- redirect to Passport login page -----------> |
   |<-- redirect back with ?code=<CODE> ----------- |
   |                        |                       |
   |-- GET /callback/?code= |                       |
   |                        |-- exchange_code_for_token() --> Passport
   |                        |<-- {access_token, ...} <------ Passport
   |                        |-- get_user_profile(access_token) -> Passport
   |                        |<-- {passport_id, first_name, ...} <- Passport
   |                        |-- find_or_create_user()
   |                        |-- generate_jwt_tokens()
   |<-- {user, access, refresh, passport_access_token}
```

---

## 📄 Litsenziya

MIT litsenziyasi ostida tarqatiladi.
Savollar va takliflar uchun **Raqamli Nazorat LLC** jamoasiga murojaat qiling.
