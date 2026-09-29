# Raqamli Passport SDK (`raqamli-passport-sdk`)

[![PyPI version](https://img.shields.io/pypi/v/raqamli-passport-sdk.svg)](https://pypi.org/project/raqamli-passport-sdk/)
[![Python Version](https://img.shields.io/badge/python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Raqamli Nazorat LLC** ekotizimidagi loyihalar uchun yagona SSO (Single Sign-On) **Passport** xizmatiga ulanish SDK kutubxonasi.

Kutubxona OAuth2 Authorization Code oqimi orqali foydalanuvchilarni autentifikatsiya qilish, profil ma'lumotlarini olish hamda Django loyihalarga minimal harakat bilan SSO imkoniyatini qo'shish uchun mo'ljallangan.

---

## 🚀 Asosiy imkoniyatlar

- **Framework-agnostic**: Istalgan Python framework (FastAPI, Flask, aiohttp) yoki oddiy scriptlar bilan ishlaydigan `PassportClient`.
- **Django & DRF tayyor integratsiyasi**: Tayyor Callback View (`PassportCallbackAPIView`) va URLs.
- **Avtomatik JWT qo'llab-quvvatlash**: Agar loyihada `djangorestframework-simplejwt` mavjud bo'lsa, foydalanuvchiga avtomatik `access` va `refresh` tokenlarini generatsiya qiladi.
- **Oson kengaytirish**: Foydalanuvchini yaratish/yangilash logikasini (`get_or_create_user`) o'z loyihangizga moslab o'zgartirish (override) imkoniyati.
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

Passport provayderidan berilgan OAuth ma'lumotlarini muhit o'zgaruvchilari (Environment Variables) yoki loyiha konfiguratsiyasiga qo'shing:

- `PASSPORT_BASE_URL`: Passport serverining asosiy manzili (masalan: `https://passport.raqamlinazorat.uz`)
- `PASSPORT_CLIENT_ID`: Loyihangiz uchun berilgan mijoz identifikatori
- `PASSPORT_CLIENT_SECRET`: Loyihangiz maxfiy kaliti
- `PASSPORT_REDIRECT_URI`: Foydalanuvchi tizimga kirgach qaytariladigan havola (Callback URL)
- `PASSPORT_TIMEOUT`: *(Ixtiyoriy)* So'rovlar uchun timeout vaqti soniyalarda (standart: `10`)

---

## 🛠 Ishlatish bo'yicha qo'llanma

### 1. Django / Django REST Framework loyihasida ishlatish

#### 1-qadam. `settings.py` ga sozlamalarni qo'shing:

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
PASSPORT_TIMEOUT = 10  # Ixtiyoriy, standart: 10 soniya
```

#### 2-qadam. `urls.py` ga tayyor yo'nalishni ulang:

```python
# urls.py
from django.urls import path, include

urlpatterns = [
    # ...
    path("api/v1/auth/passport/", include("raqamli_passport.urls")),
]
```

Bu orqali sizda quyidagi endpoint faollashadi:
- `GET /api/v1/auth/passport/callback/?code=<AUTHORIZATION_CODE>`
- `POST /api/v1/auth/passport/callback/` (Body: `{"code": "<AUTHORIZATION_CODE>"}`) — Frontend (SPA) ilovalar uchun juda qulay!

#### 3-qadam (Ixtiyoriy). Callback logikasini moslashtirish (Custom View):

Agar sizda alohida `CustomUser` modeli bo'lsa yoki qo'shimcha maydonlarni saqlash kerak bo'lsa, `PassportCallbackAPIView` dan meros oling:

```python
# views.py
from raqamli_passport.views import PassportCallbackAPIView
from django.contrib.auth import get_user_model

User = get_user_model()

class CustomPassportCallbackView(PassportCallbackAPIView):
    def get_or_create_user(self, user_data: dict):
        """
        Passport-dan kelgan ma'lumotlar:
        user_data = {
            "passport_id": 12345,
            "email": "user@example.com",
            "first_name": "Ali",
            "last_name": "Valiyev",
            "phone_number": "+998901234567"
        }
        """
        passport_id = user_data.get("passport_id")
        
        user, created = User.objects.get_or_create(
            passport_id=passport_id,
            defaults={
                "username": f"user_{passport_id}",
                "email": user_data.get("email") or "",
                "first_name": user_data.get("first_name") or "",
                "last_name": user_data.get("last_name") or "",
                "phone_number": user_data.get("phone_number") or "",
            }
        )
        return user, created
```

Uni o'zingizning `urls.py` ingizga qo'ying:
```python
# urls.py
from django.urls import path
from .views import CustomPassportCallbackView

urlpatterns = [
    path("api/v1/auth/passport/callback/", CustomPassportCallbackView.as_view(), name="passport-callback"),
]
```

---

### 2. Standart Python / FastAPI / Flask da ishlatish

Har qanday loyihada to'g'ridan-to'g'ri `PassportClient` dan foydalanishingiz mumkin:

```python
from raqamli_passport import PassportClient, PassportSDKError

# Mijozni initsializatsiya qilish
client = PassportClient(
    base_url="https://passport.raqamlinazorat.uz",
    client_id="sizning-client-id",
    client_secret="sizning-client-secret",
    redirect_uri="https://myproject.uz/callback",
    timeout=10,  # default 10 soniya
)

# 1. Foydalanuvchini yo'naltirish uchun SSO Login sahifasi havolasini olish:
auth_url = client.get_authorization_url(scope="read")
print("Login havolasi:", auth_url)
# Natija: https://passport.raqamlinazorat.uz/login?client_id=...&redirect_uri=...&scope=read

# 2. Callback orqali kelgan 'code' parametrini tekshirib, profilni olish:
# (Bir qadamda: token olish + profilni tortish)
try:
    auth_code = "frontend-yoki-url-dan-olingan-code"
    user_info = client.authenticate_code(auth_code)
    print("Foydalanuvchi ma'lumotlari:", user_info)
except PassportSDKError as exc:
    print(f"Autentifikatsiyada xatolik: {exc}")
```

#### Bosqichma-bosqich ishlash (Token va Profilni alohida olish):
```python
try:
    # 1. Kodni tokenga almashtirish
    token_response = client.exchange_code_for_token(code="auth_code")
    access_token = token_response.get("access_token")
    
    # 2. Access token orqali foydalanuvchi profilini olish
    profile = client.get_user_profile(access_token=access_token)
    print(profile)
except PassportSDKError as exc:
    print(f"Xatolik tafsiloti: {exc}")
```

---

## ⚠️ Xatoliklarni boshqarish (Exceptions)

SDK quyidagi maxsus xatolik klasslarini taqdim etadi:

- `PassportSDKError` — Barcha SDK xatoliklari uchun asosiy sinf.
- `PassportTokenExchangeError` — Kodni tokenga almashtirish jarayonida yuz bergan xatoliklar (masalan, yaroqsiz yoki muddati o'tgan `code`).
- `PassportProfileFetchError` — Foydalanuvchi ma'lumotlarini yuklab olishda yuz bergan xatoliklar (masalan, yaroqsiz `access_token`).

```python
from raqamli_passport.exceptions import (
    PassportSDKError,
    PassportTokenExchangeError,
    PassportProfileFetchError,
)

try:
    user_data = client.authenticate_code(code)
except PassportTokenExchangeError as e:
    print(f"Token olishda xatolik: {e}, Status: {e.status_code}, Tafsilot: {e.details}")
except PassportProfileFetchError as e:
    print(f"Profil olishda xatolik: {e}, Status: {e.status_code}, Tafsilot: {e.details}")
except PassportSDKError as e:
    print(f"Umumiy SDK xatosi: {e}")
```

---

## 📄 Litsenziya

Ushbu loyiha MIT litsenziyasi ostida tarqatiladi.
Qo'shimcha savollar va takliflar uchun **Raqamli Nazorat LLC** jamoasiga murojaat qiling.
