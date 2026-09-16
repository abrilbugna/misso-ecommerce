from dotenv import load_dotenv
import os
import dj_database_url
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("SECRET_KEY")

DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = ["misso-ecommerce.onrender.com", "localhost", "127.0.0.1", "misso.ar", "www.misso.ar"]

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'cloudinary',
    'cloudinary_storage',
    'tienda',
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'misso.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'frontend' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'tienda.context_processors.cart_count',
                'tienda.context_processors.subscription_offer',
            ],
        },
    },
]

WSGI_APPLICATION = 'misso.wsgi.application'

DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'es-ar'
TIME_ZONE = 'America/Argentina/Cordoba'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'frontend' / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv("CLOUDINARY_CLOUD_NAME"),
    'API_KEY': os.getenv("CLOUDINARY_API_KEY"),
    'API_SECRET': os.getenv("CLOUDINARY_API_SECRET"),
}


STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

STORAGES = {
    "default": {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_URL = '/media/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

MERCADOPAGO_PUBLIC_KEY = os.getenv("MP_PUBLIC_KEY")
MERCADOPAGO_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
SITE_URL = os.getenv("SITE_URL", "https://misso.ar").rstrip("/")

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

RESEND_API_KEY = os.getenv('RESEND_API_KEY')
NOTIFICACION_EMAIL = os.getenv('EMAIL_HOST_USER')

# One commercial definition; production reuses MP_ACCESS_TOKEN, test is isolated.
from decimal import Decimal
PUBLIC_BASE_URL = os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/')
MP_SUBSCRIPTION_MODE = os.getenv('MP_SUBSCRIPTION_MODE', 'test').strip().lower()
MP_SUBSCRIPTION_TEST_ACCESS_TOKEN = os.getenv('MP_SUBSCRIPTION_TEST_ACCESS_TOKEN', '').strip()
# Only the explicitly configured public origin is trusted for the development tunnel.
from urllib.parse import urlsplit
_public_origin = urlsplit(PUBLIC_BASE_URL)
if _public_origin.scheme == 'https' and _public_origin.hostname:
    ALLOWED_HOSTS.append(_public_origin.hostname)
    CSRF_TRUSTED_ORIGINS = [f'https://{_public_origin.netloc}']

MP_SUBSCRIPTION_ENABLED = os.getenv('MP_SUBSCRIPTION_ENABLED', 'False').lower() == 'true'
MP_SUBSCRIPTION_AMOUNT = Decimal(os.getenv('MP_SUBSCRIPTION_AMOUNT', '25000'))
MP_SUBSCRIPTION_CURRENCY = os.getenv('MP_SUBSCRIPTION_CURRENCY', 'ARS')
MP_SUBSCRIPTION_REASON = os.getenv('MP_SUBSCRIPTION_REASON', 'Misso — Suscripción mensual')
MP_SUBSCRIPTION_FREQUENCY = 1
MP_SUBSCRIPTION_FREQUENCY_TYPE = 'months'
MP_WEBHOOK_SECRET = os.getenv('MP_WEBHOOK_SECRET', '')
MISSO_ADMIN_EMAIL = os.getenv('MISSO_ADMIN_EMAIL') or NOTIFICACION_EMAIL
MISSO_EMAIL_FROM = os.getenv('MISSO_EMAIL_FROM', 'Misso <hola@misso.ar>')
# Leave blank for the documented hosted pending checkout. See docs/suscripciones.md.
MP_SUBSCRIPTION_PLAN_ID = os.getenv('MP_SUBSCRIPTION_PLAN_ID', '')

# Targeted billing audit logs; preserve the existing Django/payment loggers.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'subscription_console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        name: {'handlers': ['subscription_console'], 'level': 'INFO', 'propagate': False}
        for name in ('tienda.subscription_services', 'tienda.subscription_views', 'tienda.subscription_emails', 'tienda.subscription_api')
    },
}
