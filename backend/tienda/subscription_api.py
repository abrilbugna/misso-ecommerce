"""Small, bounded HTTP adapter. Never log provider bodies or Authorization headers."""
import re
import logging
import ipaddress
from urllib.parse import urlsplit
import requests
from django.conf import settings
from django.urls import reverse


logger = logging.getLogger(__name__)

class MPSubscriptionError(Exception):
    def __init__(self, code='mp_unavailable', uncertain=False):
        super().__init__(code)
        self.code = code
        self.uncertain = uncertain


def resource_id(value):
    value = str(value or '')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
        raise MPSubscriptionError('invalid_resource_id')
    return value


def access_token():
    mode = settings.MP_SUBSCRIPTION_MODE
    if mode == 'test':
        token = settings.MP_SUBSCRIPTION_TEST_ACCESS_TOKEN
    elif mode == 'production':
        token = settings.MERCADOPAGO_ACCESS_TOKEN
    else:
        raise MPSubscriptionError('invalid_subscription_mode')
    if not token:
        raise MPSubscriptionError('missing_test_access_token' if mode == 'test' else 'mp_not_configured')
    return token


def public_base():
    base = settings.PUBLIC_BASE_URL or (settings.SITE_URL if settings.MP_SUBSCRIPTION_MODE == 'production' else '')
    try:
        url = urlsplit(base)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ('', '/')
                or url.hostname == 'localhost' or url.hostname.endswith('.localhost')):
            raise ValueError
        try:
            address = ipaddress.ip_address(url.hostname)
        except ValueError:
            if '.' not in url.hostname or re.search(r'[^a-zA-Z0-9.-]', url.hostname):
                raise ValueError
        else:
            if not address.is_global:
                raise ValueError
        _ = url.port
    except ValueError:
        raise MPSubscriptionError('invalid_public_base_url') from None
    return base.rstrip('/')


def public_url(route, **kwargs):
    # Terms/emails remain available before the checkout has been configured.
    return (settings.PUBLIC_BASE_URL or settings.SITE_URL).rstrip('/') + reverse(route, kwargs=kwargs)


def safe_diagnostic(value):
    if not isinstance(value, (str, int)):
        return '-'
    value = str(value)
    for secret in (settings.MERCADOPAGO_ACCESS_TOKEN, settings.MP_SUBSCRIPTION_TEST_ACCESS_TOKEN,
                   settings.MP_WEBHOOK_SECRET, settings.RESEND_API_KEY):
        if secret:
            value = value.replace(secret, '[redacted]')
    value = re.sub(r'(?i)(bearer\s+|(?:access_token|token|secret)[=: ]+)[^\s,;]+', '[redacted]', value)
    value = re.sub(r'[^\s@]+@[^\s@]+', '[email]', value)
    value = re.sub(r'\b(?:APP_USR|TEST)-[\w-]+|\b\d{12,}\b', '[redacted]', value)
    return ' '.join(value.split())[:400]


def terms_url():
    return public_url('informacion_suscripcion') + '#terminos'


def checkout_url(value):
    url = urlsplit(str(value or ''))
    if url.scheme != 'https' or url.netloc not in ('www.mercadopago.com.ar', 'www.mercadopago.com.ar:443') or url.path != '/subscriptions/checkout':
        raise MPSubscriptionError('invalid_init_point', uncertain=True)
    return value


class SubscriptionAPI:
    def request(self, method, path, *, payload=None, params=None):
        token = access_token()
        try:
            response = requests.request(method, 'https://api.mercadopago.com' + path,
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json=payload, params=params, timeout=(3, 8), allow_redirects=False)
        except requests.RequestException as exc:
            logger.warning("[SUBSCRIPTION] transport_error type=%s", type(exc).__name__)
            raise MPSubscriptionError('mp_transport_error', uncertain=method == 'POST') from None
        if not 200 <= response.status_code < 300:
            try:
                error = response.json()
            except ValueError:
                error = {}
            if not isinstance(error, dict):
                error = {}
            logger.warning('[SUBSCRIPTION] API status=%s type=%s message=%s request_id=%s',
                response.status_code, safe_diagnostic(error.get('error')),
                safe_diagnostic(error.get('message')),
                safe_diagnostic(response.headers.get('x-request-id') or response.headers.get('x-correlation-id')))
            raise MPSubscriptionError(f'mp_http_{response.status_code}', uncertain=method == 'POST' and response.status_code not in (400, 401, 403, 404, 422))
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return data
        except ValueError:
            raise MPSubscriptionError('mp_invalid_response', uncertain=method == 'POST') from None

    def get_subscription(self, identifier):
        return self.request('GET', f'/preapproval/{resource_id(identifier)}')

    def search_subscription(self, reference):
        return self.request('GET', '/preapproval/search', params={'external_reference': reference, 'limit': 100})

    def create_pending(self, sub):
        # Associated plans require card_token_id + authorized; do not silently mix flows.
        if settings.MP_SUBSCRIPTION_PLAN_ID:
            raise MPSubscriptionError('associated_plan_requires_card_token')
        access_token()
        base = public_base()
        return self.request('POST', '/preapproval', payload={
            'reason': settings.MP_SUBSCRIPTION_REASON,
            'external_reference': sub.external_reference,
            'payer_email': sub.email,
            'auto_recurring': {'frequency': sub.frecuencia, 'frequency_type': sub.frecuencia_tipo,
                               'transaction_amount': float(sub.importe), 'currency_id': sub.moneda},
            'back_url': base + reverse('suscripcion_resultado', kwargs={'referencia': sub.referencia_publica}),
            'notification_url': base + reverse('suscripciones_webhook') + '?source_news=webhooks',
            'status': 'pending',
        })

    def get_invoice(self, identifier):
        return self.request('GET', f'/authorized_payments/{resource_id(identifier)}')

    def invoices_for_payment(self, identifier):
        return self.request('GET', '/authorized_payments/search', params={'payment_id': resource_id(identifier), 'limit': 100})

    def get_payment(self, identifier):
        return self.request('GET', f'/v1/payments/{resource_id(identifier)}')
