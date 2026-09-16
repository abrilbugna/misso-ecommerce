"""Isolated tests: no use of the database/credentials configured in .env."""
from .settings import *
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
MERCADOPAGO_ACCESS_TOKEN = 'test-not-a-credential'
RESEND_API_KEY = 'test-not-a-credential'
MP_SUBSCRIPTION_ENABLED = False
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
