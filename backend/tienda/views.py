from django.shortcuts import render, redirect, get_object_or_404
from .models import Producto, Carrito, ItemCarrito, Orden, ItemOrden, CATEGORIAS, ColorProducto, TalleProducto, CodigoPromocional
from .forms import CheckoutForm
from .email_utils import enviar_notificacion_tienda, enviar_comprobante_cliente
import mercadopago
from django.conf import settings
from django.http import JsonResponse
import json


def inicio(request):
    categorias_con_imagen = []

    productos_por_categoria = (
        Producto.objects
        .filter(activo=True)
        .prefetch_related('imagenes')
        .order_by('categoria')
    )

    productos_dict = {}
    for p in productos_por_categoria:
        if p.categoria not in productos_dict:
            productos_dict[p.categoria] = p

    for slug, nombre in CATEGORIAS:
        producto = productos_dict.get(slug)
        if producto:
            imagen_url = producto.get_imagen_url()
            if imagen_url:
                categorias_con_imagen.append({
                    'slug': slug,
                    'nombre': nombre,
                    'imagen': imagen_url,
                })

    return render(request, 'tienda/inicio.html', {'categorias': categorias_con_imagen})


def catalogo(request):
    categoria = request.GET.get('categoria', '')
    busqueda = request.GET.get('q', '')

    productos = Producto.objects.filter(activo=True).prefetch_related('imagenes')

    if categoria:
        productos = productos.filter(categoria=categoria)
    if busqueda:
        productos = productos.filter(nombre__icontains=busqueda)

    return render(request, 'tienda/catalogo.html', {
        'productos': productos,
        'categoria_activa': categoria,
        'categorias': CATEGORIAS,
        'busqueda': busqueda,
    })


def detalle(request, pk):
    producto = get_object_or_404(
        Producto.objects.prefetch_related('colores', 'colores__talles', 'imagenes', 'videos'),
        pk=pk
    )
    error = request.GET.get('error', '')
    return render(request, 'tienda/detalle.html', {
        'producto': producto,
        'error': error
    })


def talles_por_color(request, color_id):
    color = get_object_or_404(ColorProducto, pk=color_id)
    talles = [
        {'id': t.id, 'talle': t.talle, 'stock': t.stock}
        for t in color.talles.all().order_by('talle')
    ]
    return JsonResponse({'talles': talles})


def agregar_carrito(request, pk):
    producto = get_object_or_404(Producto, pk=pk)

    color_id = request.GET.get('color')
    talle_id = request.GET.get('talle')
    cantidad = int(request.GET.get('cantidad', 1))

    if not request.session.session_key:
        request.session.create()

    carrito, _ = Carrito.objects.get_or_create(session_key=request.session.session_key)

    if not producto.colores.exists():
        item, creado = ItemCarrito.objects.get_or_create(
            carrito=carrito,
            producto=producto,
            color=None,
            talle=None
        )
        if not creado:
            item.cantidad += cantidad
        else:
            item.cantidad = cantidad
        item.save()
        return redirect('ver_carrito')

    if not color_id:
        return redirect(f'/tienda/{pk}/?error=color')

    if not talle_id:
        return redirect(f'/tienda/{pk}/?error=talle&color={color_id}')

    color = get_object_or_404(ColorProducto, pk=color_id, producto=producto)
    talle = get_object_or_404(TalleProducto, pk=talle_id, color=color)

    if talle.stock <= 0:
        return redirect(f'/tienda/{pk}/?error=stock&color={color_id}&talle={talle_id}')

    item, creado = ItemCarrito.objects.get_or_create(
        carrito=carrito,
        producto=producto,
        color=color,
        talle=talle
    )
    if not creado:
        item.cantidad += cantidad
    else:
        item.cantidad = cantidad
    item.save()

    return redirect(f'/tienda/{pk}/?agregado=1')


def ver_carrito(request):
    if not request.session.session_key:
        request.session.create()

    carrito, _ = Carrito.objects.get_or_create(session_key=request.session.session_key)
    items = ItemCarrito.objects.filter(carrito=carrito)

    total = sum(item.subtotal() for item in items)

    codigo_aplicado = request.session.get('codigo_promo')
    descuento = 0
    if codigo_aplicado:
        try:
            codigo = CodigoPromocional.objects.get(codigo=codigo_aplicado)
            if codigo.es_valido():
                descuento = codigo.calcular_descuento(total)
            else:
                del request.session['codigo_promo']
                codigo_aplicado = None
        except CodigoPromocional.DoesNotExist:
            del request.session['codigo_promo']
            codigo_aplicado = None

    return render(request, 'tienda/carrito.html', {
        'items': items,
        'total': total,
        'descuento': descuento,
        'total_con_descuento': total - descuento,
        'codigo_aplicado': codigo_aplicado,
    })


def aplicar_codigo(request):
    if request.method != 'POST':
        return JsonResponse({'valido': False, 'mensaje': 'Método no permitido'})

    data = json.loads(request.body)
    codigo_str = data.get('codigo', '').strip().upper()

    try:
        codigo = CodigoPromocional.objects.get(codigo__iexact=codigo_str)
        if not codigo.es_valido():
            return JsonResponse({'valido': False, 'mensaje': 'Código inválido o expirado'})

        if not request.session.session_key:
            request.session.create()
        carrito, _ = Carrito.objects.get_or_create(session_key=request.session.session_key)
        items = ItemCarrito.objects.filter(carrito=carrito)
        subtotal = sum(item.subtotal() for item in items)
        descuento = codigo.calcular_descuento(subtotal)

        request.session['codigo_promo'] = codigo.codigo

        return JsonResponse({
            'valido': True,
            'codigo': codigo.codigo,
            'descuento': float(descuento),
            'total_con_descuento': float(subtotal - descuento),
            'mensaje': str(codigo),
        })
    except CodigoPromocional.DoesNotExist:
        return JsonResponse({'valido': False, 'mensaje': 'Código no encontrado'})


def eliminar_codigo(request):
    if 'codigo_promo' in request.session:
        del request.session['codigo_promo']
    return redirect('ver_carrito')


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

    codigo_aplicado = request.session.get('codigo_promo')
    descuento = 0
    codigo_obj = None
    if codigo_aplicado:
        try:
            codigo_obj = CodigoPromocional.objects.get(codigo=codigo_aplicado)
            if codigo_obj.es_valido():
                descuento = codigo_obj.calcular_descuento(subtotal)
            else:
                del request.session['codigo_promo']
                codigo_obj = None
        except CodigoPromocional.DoesNotExist:
            del request.session['codigo_promo']

    if request.method == 'POST':
        form = CheckoutForm(request.POST)

        if form.is_valid():
            envio = form.cleaned_data['envio']
            metodo_pago = form.cleaned_data['metodo_pago']
            total = subtotal - descuento + envio.costo

            orden = Orden.objects.create(
                nombre=form.cleaned_data['nombre'],
                email=form.cleaned_data['email'],
                telefono=form.cleaned_data['telefono'],
                direccion=form.cleaned_data['direccion'],
                envio=envio,
                metodo_pago=metodo_pago,
                subtotal=subtotal,
                descuento=descuento,
                codigo_promo=codigo_obj,
                total=total,
                estado='en_proceso',
            )

            if codigo_obj:
                codigo_obj.usos_actuales += 1
                codigo_obj.save()
                del request.session['codigo_promo']

            items_guardados = []
            for item in items:
                item_orden = ItemOrden.objects.create(
                    orden=orden,
                    producto=item.producto,
                    cantidad=item.cantidad,
                    precio=item.producto.precio,
                    color=item.color,
                    talle=item.talle,
                )
                items_guardados.append(item_orden)
                if item.talle:
                    item.talle.stock = max(0, item.talle.stock - item.cantidad)
                    item.talle.save()

            try:
                enviar_notificacion_tienda(orden, items_guardados)
                if metodo_pago != 'mercadopago':
                    enviar_comprobante_cliente(orden)
            except Exception:
                pass

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
        'descuento': descuento,
        'total_con_descuento': subtotal - descuento,
        'codigo_aplicado': codigo_aplicado,
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
            "success": f"https://misso.ar/tienda/confirmacion/{orden.pk}/",
            "failure": f"https://misso.ar/tienda/carrito/",
            "pending": f"https://misso.ar/tienda/confirmacion/{orden.pk}/",
        },
        "auto_return": "approved",
        "external_reference": str(orden.pk),
    }

    preference_response = sdk.preference().create(preference_data)
    preference = preference_response["response"]
    mp_url = preference.get("init_point")

    if not mp_url:
        return redirect('ver_carrito')

    return redirect(mp_url)
