"""Private order links and checkout ownership, independent of user accounts."""
from time import time
from django.conf import settings
from django.urls import reverse


def tracking_url(order):
    return settings.SITE_URL.rstrip('/') + reverse('seguir_pedido_token', args=[order.seguimiento_token])


def remember_checkout(request, order):
    keys = request.session.get('checkout_orders', [])
    request.session['checkout_orders'] = [*keys[-19:], str(order.seguimiento_token)]


def can_access_order(request, order):
    token = str(order.seguimiento_token)
    if token in request.session.get('checkout_orders', []):
        return True
    access = request.session.get('tracking_access', {})
    return access.get('token') == token and access.get('expires', 0) > time()
