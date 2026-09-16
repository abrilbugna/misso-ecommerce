from .models import Carrito, ItemCarrito

def cart_count(request):
    count = 0
    if request.session.session_key:
        try:
            carrito = Carrito.objects.get(session_key=request.session.session_key)
            count = ItemCarrito.objects.filter(carrito=carrito).count()
        except Carrito.DoesNotExist:
            pass
    return {'cart_count': count}


def subscription_offer(request):
    """The public amount and the API use the same commercial setting."""
    from django.conf import settings
    amount = settings.MP_SUBSCRIPTION_AMOUNT
    whole, fraction = f'{amount:.2f}'.split('.')
    display = format(int(whole), ',').replace(',', '.')
    if fraction != '00':
        display += ',' + fraction
    compact = f'{int(amount / 1000)}K' if amount % 1000 == 0 else display
    return {'subscription_price_display': display, 'subscription_price_compact': compact}
