# Raqamli Passport SDK (`raqamli-passport-sdk`)

[![PyPI version](https://img.shields.io/pypi/v/raqamli-passport-sdk.svg)](https://pypi.org/project/raqamli-passport-sdk/)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Raqamli Nazorat LLC** ekotizimidagi loyihalar uchun yagona SSO (Single Sign-On) **Passport** xizmatiga ulanish SDK kutubxonasi.

Kutubxona OAuth2 Authorization Code oqimi orqali foydalanuvchilarni autentifikatsiya qilish, profil ma'lumotlarini olish, webhook orqali avtomatik sinxronizatsiya qilish hamda Django loyihalarga minimal harakat bilan SSO imkoniyatini qo'shish uchun mo'ljallangan.

---

## 🚀 Asosiy imkoniyatlar

- **Framework-agnostic**: Istalgan Python framework (FastAPI, Flask, aiohttp) yoki oddiy scriptlar bilan ishlaydigan `PassportClient`.
- **Django & DRF tayyor integratsiyasi**:
  - `callback/` — Login va avtorizatsiya kodi (`code`) orqali tizimga kirish (`PassportCallbackAPIView`).
  - `webhook/` — Passport SSO dan foydalanuvchi ma'lumotlari o'zgarganda avtomatik yangilovchi endpoint (`PassportWebhookAPIView`).
  - `sync/` — Foydalanuvchi profilini qo'lda (manual) Passport bilan qayta sinxronizatsiya qilish endpointi (`PassportSyncProfileAPIView`).
- **To'liq ma'lumotlar sinxronizatsiyasi**:
  - Passport-dan keladigan barcha ma'lumotlar (`first_name`, `last_name`, `email`, `phone`/`phone_number`, `avatar`, `birth_date`, `passport_id`) User modelida mavjud bo'lsa avtomatik to'ldiriladi va yangilanadi.
  - *Eslatma:* Viloyat (`region`) va tuman (`district`) ID raqamlari turli loyihalarda farq qilishi mumkinligi sababli, kutubxona ularni avtomatik bog'lamaydi. Loyiha o'zining hududiy ma'lumotlar bazasiga moslab metodlarni osongina override qilishi mumkin.
- **HMAC SHA-256 Webhook xavfsizligi**: Passport serveridan yuboriladigan `X-SSO-Signature` imzosini avtomatik tekshirish.
- **Avtomatik JWT qo'llab-quvvatlash**: Agar loyihada `djangorestframework-simplejwt` mavjud bo'lsa, foydalanuvchiga avtomatik `access` va `refresh` tokenlarini generatsiya qiladi.
- **Aniq xatoliklar tizimi**: Xatolarni tezkor ushlash va aniqlash uchun maxsus istisnolar (`PassportSDKError`).

---

## 📦 O'rnatish

### Standart o'rnatish (Faqat mijoz - FastAPI, Flask, scriptlar uchun):
```bash
pip install raqamli-passport-sdk
```

### Django / Django REST Framework bilan o'rnatish:
```bash
pip install "raqamli-passport-sdk[django]"
```

---

## ⚙️ Sozlash (Configuration)

Passport provayderidan berilgan OAuth va Webhook ma'lumotlarini muhit o'zgaruvchilari yoki Django `settings.py` fayliga qo'shing:

- `PASSPORT_BASE_URL`: Passport serverining asosiy manzili (masalan: `https://passport.raqamlinazorat.uz`)
- `PASSPORT_CLIENT_ID`: Loyihangiz uchun berilgan mijoz identifikatori
- `PASSPORT_CLIENT_SECRET`: Loyihangiz maxfiy kaliti
- `PASSPORT_WEBHOOK_SECRET`: Webhook imzosini (HMAC SHA-256) tekshirish uchun maxfiy kalit (Passport tizimida webhook ulanganda beriladigan maxsus secret kalit)
- `PASSPORT_TIMEOUT`: *(Ixtiyoriy)* So'rovlar uchun timeout vaqti soniyalarda (standart: `10`)

---

## 🛠 Django / DRF Loyihasida ishlatish

### 1-qadam. `settings.py` sozlamalari:

```python
# settings.py

INSTALLED_APPS = [
    # ...
    "rest_framework",
    # Agar JWT ishlatmoqchi bo'lsangiz:
    "rest_framework_simplejwt",
    # ...
]

PASSPORT_BASE_URL = "https://passport.raqamlinazorat.uz"
PASSPORT_CLIENT_ID = "sizning-client-id"
PASSPORT_CLIENT_SECRET = "sizning-client-secret"
PASSPORT_REDIRECT_URI = "https://myproject.uz/api/v1/auth/passport/callback/"
PASSPORT_WEBHOOK_SECRET = "sizning-webhook-secret"  # Ixtiyoriy
PASSPORT_TIMEOUT = 10  # Ixtiyoriy, standart: 10 soniya
```

### 2-qadam. `urls.py` ga tayyor yo'nalishlarni ulang:

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    # ...
    path("api/v1/auth/passport/", include("raqamli_passport.urls")),
]
```

Bu orqali loyihangizda 3 ta tayyor endpoint faollashadi:
1. `GET /api/v1/auth/passport/callback/?code=<CODE>` yoki `POST /api/v1/auth/passport/callback/` (`{"code": "..."}`) — Tizimga kirish.
2. `POST /api/v1/auth/passport/webhook/` — Passport serveridan avtomatik yangilanishlarni qabul qilish.
3. `POST /api/v1/auth/passport/sync/` (yoki `GET`) — Tizimga kirgan foydalanuvchi profilini qo'lda Passport bilan yangilash.

---

### 🔄 Avtomatik Sinxronizatsiya (Webhook)

Passport SSO foydalanuvchi ma'lumotlari o'zgarganda ulangan ilovalarning webhook manziliga yangilangan ma'lumotlarni yuboradi.

SDK ushbu webhook so'rovini qabul qilib:
1. `X-SSO-Signature` (HMAC SHA-256) orqali so'rov haqiqiyligini tekshiradi.
2. Bazadan foydalanuvchini topadi (`passport_id`, `username`, `phone_number` yoki `email` orqali).
3. Foydalanuvchining barcha o'zgargan maydonlarini avtomatik yangilab saqlaydi.

---

### ✋ Qo'lda Sinxronizatsiya (Manual Sync)

Har ehtimolga qarshi (masalan foydalanuvchi o'z ma'lumotlarini Passportda o'zgartirib qaytganda), foydalanuvchi profilini qo'lda yangilash mumkin:

- **Endpoint:** `POST /api/v1/auth/passport/sync/`
- **Ruxsat:** `IsAuthenticated` (tizimga kirgan foydalanuvchi)
- **Parametrlar:** `{"access_token": "<PASSPORT_ACCESS_TOKEN>"}`

Endpoint Passport serveriga bog'lanib, eng so'nggi ma'lumotlarni tortib oladi va lokal bazadagi userni yangilaydi.

---

### 🧩 Maxsus User modeli va Hududlarni (Viloyat/Tuman) moslashtirish

Agar loyihangizda viloyat (`region`) va tuman (`district`) modellari bo'lsa, ularni osongina `get_or_create_user` yoki `sync_user` metodlarini override qilish orqali bog'lab olishingiz mumkin:

```python
# views.py
from raqamli_passport.views import PassportCallbackAPIView, PassportWebhookAPIView
from my_geo_app.models import Region, District

class CustomPassportCallbackView(PassportCallbackAPIView):
    def get_or_create_user(self, user_data: dict):
        user, created = super().get_or_create_user(user_data)
        
        # Viloyat va tumanni lokal bazaga moslab bog'lash:
        region_data = user_data.get("region")   # {"id": 1, "name": "Toshkent"}
        district_data = user_data.get("district") # {"id": 2, "name": "Yunusobod"}
        
        if region_data and hasattr(user, "region"):
            user.region = Region.objects.filter(name__iexact=region_data.get("name")).first()
        if district_data and hasattr(user, "district"):
            user.district = District.objects.filter(name__iexact=district_data.get("name")).first()
            
        user.save()
        return user, created


class CustomPassportWebhookView(PassportWebhookAPIView):
    def sync_user(self, user_data: dict):
        user = super().sync_user(user_data)
        # Webhook kelganda ham viloyat/tumanni yangilash logikasi:
        # ...
        return user
```

---

## 🐍 Standart Python / FastAPI / Flask da ishlatish

Istalgan mustaqil Python dasturida:

```python
from raqamli_passport import PassportClient, verify_webhook_signature, PassportSDKError

client = PassportClient(
    base_url="https://passport.raqamlinazorat.uz",
    client_id="sizning-client-id",
    client_secret="sizning-client-secret",
    redirect_uri="https://myproject.uz/callback",
    webhook_secret="sizning-webhook-secret",
)

# 1. Login havolasi olish:
auth_url = client.get_authorization_url(scope="read", state="random_csrf_token")

# 2. Kodni tekshirib foydalanuvchi ma'lumotlarini olish:
user_info = client.authenticate_code(code="authorization_code")

# 3. Webhook imzosini tekshirish:
is_valid = client.verify_webhook_signature(
    payload_bytes=raw_request_body,
    signature=request_headers.get("X-SSO-Signature"),
)
```

---

## ⚠️ Xatoliklarni boshqarish (Exceptions)

- `PassportSDKError` — Barcha SDK xatoliklari uchun asosiy sinf.
- `PassportTokenExchangeError` — Kodni tokenga almashtirishdagi xatolik.
- `PassportProfileFetchError` — Profil ma'lumotlarini olishdagi xatolik.
- `PassportWebhookSignatureError` — Webhook imzosini tekshirishdagi xatolik.

---

## 📄 Litsenziya

Ushbu loyiha MIT litsenziyasi ostida tarqatiladi.
Qo'shimcha savollar va takliflar uchun **Raqamli Nazorat LLC** jamoasiga murojaat qiling.
