from django.shortcuts import render, redirect, get_object_or_404
from .models import Producto, Carrito, ItemCarrito, Orden, ItemOrden, CATEGORIAS
from .forms import CheckoutForm
import mercadopago
from django.conf import settings

def inicio(request):
    categorias_con_imagen = []
    for slug, nombre in CATEGORIAS:
        producto = Producto.objects.filter(activo=True, categoria=slug).first()
        if producto:
            categorias_con_imagen.append({
                'slug': slug,
                'nombre': nombre,
                'imagen': producto.imagen.url,
            })
    return render(request, 'tienda/inicio.html', {'categorias': categorias_con_imagen})

def catalogo(request):
    categoria = request.GET.get('categoria', '')
    if categoria:
        productos = Producto.objects.filter(activo=True, categoria=categoria)
    else:
        productos = Producto.objects.filter(activo=True)
    return render(request, 'tienda/catalogo.html', {
        'productos': productos,
        'categoria_activa': categoria,
        'categorias': CATEGORIAS,
    })

def detalle(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    return render(request, 'tienda/detalle.html', {'producto': producto})

def agregar_carrito(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if not request.session.session_key:
        request.session.create()
    carrito, _ = Carrito.objects.get_or_create(session_key=request.session.session_key)
    item, creado = ItemCarrito.objects.get_or_create(carrito=carrito, producto=producto)
    if not creado:
        item.cantidad += 1
        item.save()
    return redirect('ver_carrito')

def ver_carrito(request):
    if not request.session.session_key:
        request.session.create()
    carrito, _ = Carrito.objects.get_or_create(session_key=request.session.session_key)
    items = ItemCarrito.objects.filter(carrito=carrito)
    total = sum(item.subtotal() for item in items)
    return render(request, 'tienda/carrito.html', {'items': items, 'total': total})

def eliminar_carrito(request, pk):
    item = get_object_or_404(ItemCarrito, pk=pk)
    item.delete()
    return redirect('ver_carrito')

def checkout(request):
    if not request.session.session_key:
        return redirect('catalogo')
    carrito, _ = Carrito.objects.get_or_create(session_key=request.session.session_key)
    items = ItemCarrito.objects.filter(carrito=carrito)
    if not items:
        return redirect('ver_carrito')
    
    subtotal = sum(item.subtotal() for item in items)
    
    if request.method == 'POST':
        form = CheckoutForm(request.POST)
        if form.is_valid():
            envio = form.cleaned_data['envio']
            metodo_pago = form.cleaned_data['metodo_pago']
            total = subtotal + envio.costo
            
            orden = Orden.objects.create(
                nombre=form.cleaned_data['nombre'],
                email=form.cleaned_data['email'],
                telefono=form.cleaned_data['telefono'],
                direccion=form.cleaned_data['direccion'],
                envio=envio,
                metodo_pago=metodo_pago,
                total=total
            )
            for item in items:
                ItemOrden.objects.create(
                    orden=orden,
                    producto=item.producto,
                    cantidad=item.cantidad,
                    precio=item.producto.precio
                )
            items.delete()

            if metodo_pago == 'efectivo':
                return redirect('confirmacion', pk=orden.pk)
            elif metodo_pago == 'transferencia':
                return redirect('confirmacion_transferencia', pk=orden.pk)
            elif metodo_pago == 'mercadopago':
                return redirect('pago_mp', pk=orden.pk)
    else:
        form = CheckoutForm()
    
    return render(request, 'tienda/checkout.html', {
        'form': form,
        'items': items,
        'subtotal': subtotal,
        'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
    })

def confirmacion(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    return render(request, 'tienda/confirmacion.html', {'orden': orden})

def confirmacion_transferencia(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    return render(request, 'tienda/confirmacion_transferencia.html', {'orden': orden})

def pago_mp(request, pk):
    orden = get_object_or_404(Orden, pk=pk)
    
    sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
    items = ItemOrden.objects.filter(orden=orden)
    
    preference_data = {
    "items": [
        {
            "title": item.producto.nombre,
            "quantity": item.cantidad,
            "unit_price": float(item.precio),
        }
        for item in items
    ],
    "back_urls": {
        "success": "https://www.google.com",
        "failure": "https://www.google.com",
        "pending": "https://www.google.com",
    },
    "external_reference": str(orden.pk),
}
    
    preference_response = sdk.preference().create(preference_data)
    print("RESPUESTA MP:", preference_response)
    preference = preference_response["response"]
    
    return render(request, 'tienda/pago_mp.html', {
        'orden': orden,
        'mp_url': preference.get("sandbox_init_point") or preference.get("init_point"),
    })