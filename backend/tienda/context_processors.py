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
