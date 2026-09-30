"""Pause the public experience without disabling historical payment processing."""
from functools import wraps

from django.conf import settings
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache


def public_subscription_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not settings.SUBSCRIPTIONS_PUBLIC_ENABLED:
            return redirect('catalogo')
        return view(request, *args, **kwargs)

    # Neither the disabled redirect nor an enabled form should survive a toggle
    # in a browser/proxy cache. The redirect must not preserve a submitted POST.
    return never_cache(wrapped)
