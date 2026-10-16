"""DNI matching only: never persist the document number itself."""
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.crypto import constant_time_compare, salted_hmac


def normalize_dni(value):
    value = str(value).strip()
    if not re.fullmatch(r'(?:[0-9]{7,8}|[0-9]{1,2}\.[0-9]{3}\.[0-9]{3})', value):
        raise ValidationError('Ingresá un DNI de 7 u 8 dígitos, con o sin puntos.')
    value = value.replace('.', '')
    if int(value) == 0:
        raise ValidationError('Ingresá un DNI válido.')
    return value


def dni_digest(value, order_token):
    # Per-order token prevents linking buyers by comparing stored digests.
    value = normalize_dni(value)
    return 'v1:' + salted_hmac('misso-order-dni-v1', f'{order_token}:{value}',
                              secret=settings.ORDER_DNI_KEY, algorithm='sha256').hexdigest()


def matches_dni(order, value):
    return bool(order.dni_hash) and constant_time_compare(order.dni_hash, dni_digest(value, order.seguimiento_token))
