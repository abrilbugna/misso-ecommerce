from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction, OperationalError
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .models import Producto, Carrito, ItemCarrito, Orden, ItemOrden, CATEGORIAS, ColorProducto, TalleProducto, CodigoPromocional, OpcionEnvio
from .forms import CheckoutForm
from .order_identity import dni_digest
from django.views.decorators.debug import sensitive_post_parameters
from .subscription_access import public_subscription_required
from .order_emails import queue_initial
from .order_services import confirm_verified_payment
from .order_access import remember_checkout, can_access_order
import mercadopago
from django.conf import settings
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from .inventory import requirements, adjust_locked
import json


MERCADOPAGO_RECARGO = Decimal('0.10')


def _total_mercadopago(total_sin_recargo):
    return (total_sin_recargo * (Decimal('1.00') + MERCADOPAGO_RECARGO)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )


def inicio(request):
    categorias_con_imagen = []
    productos_inicio = []

    productos_por_categoria = (
        Producto.objects
        .filter(activo=True)
        .prefetch_related('imagenes')
        .order_by('categoria')
    )

    productos_dict = {}
    for p in productos_por_categoria:
        imagen = next(iter(p.imagenes.all()), None)
        if not imagen:
            continue
        imagen_url = imagen.imagen.url
        productos_inicio.append({
            'id': p.pk,
            'nombre': p.nombre,
            'imagen': imagen_url,
            'destacado': p.destacado,
            'creado': p.creado,
        })
        if p.categoria not in productos_dict:
            productos_dict[p.categoria] = imagen_url

    for slug, nombre in CATEGORIAS:
        imagen_url = productos_dict.get(slug)
        if imagen_url:
            categorias_con_imagen.append({
                'slug': slug,
                'nombre': nombre,
                'imagen': imagen_url,
            })

    productos_inicio.sort(key=lambda p: (p['destacado'], p['creado']), reverse=True)
    return render(request, 'tienda/inicio.html', {
        'categorias': categorias_con_imagen,
        'productos_inicio': productos_inicio[:12],
    })


@public_subscription_required
def informacion_suscripcion(request):
    return render(request, 'tienda/informacion_suscripcion.html')



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
    colores_conjunto = []
    if producto.tipo == 'conjunto' and producto.parte_superior_id and producto.parte_inferior_id:
        top_colors = ColorProducto.objects.filter(producto=producto.parte_superior).prefetch_related('talles')
        bottom_names = {c.casefold() for c in ColorProducto.objects.filter(producto=producto.parte_inferior).values_list('nombre', flat=True)}
        colores_conjunto = [c for c in top_colors if c.nombre.casefold() in bottom_names]
    return render(request, 'tienda/detalle.html', {
        'producto': producto,
        'error': error,
        'colores_conjunto': colores_conjunto,
    })


def talles_por_color(request, color_id):
    color = get_object_or_404(ColorProducto, pk=color_id)
    talles = [
        {'id': t.id, 'talle': t.talle, 'stock': t.stock}
        for t in color.talles.all().order_by('talle')
    ]
    return JsonResponse({'talles': talles})


def talles_conjunto(request, pk, color_id):
    producto = get_object_or_404(Producto, pk=pk, tipo='conjunto', activo=True)
    top_color = get_object_or_404(ColorProducto, pk=color_id, producto_id=producto.parte_superior_id)
    bottom_color = ColorProducto.objects.filter(producto_id=producto.parte_inferior_id, nombre__iexact=top_color.nombre).first()
    if bottom_color is None:
        return JsonResponse({'superior': [], 'inferior': []})
    def sizes(color):
        return [{'id': size.pk, 'talle': size.talle, 'stock': size.stock} for size in color.talles.order_by('talle')]
    return JsonResponse({'superior': sizes(top_color), 'inferior': sizes(bottom_color)})


@transaction.atomic
def agregar_carrito(request, pk):
    producto = get_object_or_404(Producto, pk=pk, activo=True)

    color_id = request.GET.get('color')
    talle_id = request.GET.get('talle')
    try:
        cantidad = int(request.GET.get('cantidad', 1))
    except (ValueError, TypeError):
        cantidad = 0
    if not 1 <= cantidad <= 99:
        return redirect(f'/tienda/{pk}/?error=cantidad')

    if not request.session.session_key:
        request.session.create()

    carrito, _ = Carrito.objects.get_or_create(session_key=request.session.session_key)
    carrito = Carrito.objects.select_for_update().get(pk=carrito.pk)

    if producto.tipo == 'conjunto':
        bottom_id = request.GET.get('talle_inferior')
        if not color_id or not talle_id or not bottom_id:
            return redirect(f'/tienda/{pk}/?error=talle')
        top_color = get_object_or_404(ColorProducto, pk=color_id, producto_id=producto.parte_superior_id)
        top = get_object_or_404(TalleProducto, pk=talle_id, color=top_color)
        bottom = get_object_or_404(TalleProducto, pk=bottom_id, color__producto_id=producto.parte_inferior_id,
                                  color__nombre__iexact=top_color.nombre)
        item, created = ItemCarrito.objects.get_or_create(carrito=carrito, producto=producto, color=top_color,
                                                          talle=top, talle_inferior=bottom)
        wanted = item.cantidad + cantidad if not created else cantidad
        if top.stock < wanted or bottom.stock < wanted:
            if created:
                item.delete()
            return redirect(f'/tienda/{pk}/?error=stock')
        item.cantidad = wanted
        item.save(update_fields=['cantidad'])
        if not _cart_has_stock(carrito):
            if created:
                item.delete()
            else:
                item.cantidad -= cantidad
                item.save(update_fields=['cantidad'])
            return redirect(f'/tienda/{pk}/?error=stock')
        return redirect(f'/tienda/{pk}/?agregado=1')

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
        if item.cantidad > 99:
            return redirect(f'/tienda/{pk}/?error=cantidad')
        item.save()
        return redirect('ver_carrito')

    if not color_id:
        return redirect(f'/tienda/{pk}/?error=color')

    if not talle_id:
        return redirect(f'/tienda/{pk}/?error=talle&color={color_id}')

    color = get_object_or_404(ColorProducto, pk=color_id, producto=producto)
    talle = get_object_or_404(TalleProducto, pk=talle_id, color=color)

    if talle.stock < cantidad:
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
    if item.cantidad > talle.stock or item.cantidad > 99:
        if creado:
            item.delete()
        return redirect(f'/tienda/{pk}/?error=stock&color={color_id}&talle={talle_id}')
    item.save()
    if not _cart_has_stock(carrito):
        if creado:
            item.delete()
        else:
            item.cantidad -= cantidad
            item.save(update_fields=['cantidad'])
        return redirect(f'/tienda/{pk}/?error=stock&color={color_id}&talle={talle_id}')

    return redirect(f'/tienda/{pk}/?agregado=1')


def _cart_has_stock(carrito):
    try:
        quantities = requirements(ItemCarrito.objects.select_related(
            'producto', 'talle__color', 'talle_inferior__color').filter(carrito=carrito))
    except ValidationError:
        return False
    stocks = dict(TalleProducto.objects.filter(pk__in=quantities).values_list('pk', 'stock'))
    return all(stocks.get(pk, -1) >= count for pk, count in quantities.items())


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


@transaction.atomic
def eliminar_carrito(request, pk):
    if not request.session.session_key:
        return redirect('ver_carrito')
    carrito = get_object_or_404(Carrito.objects.select_for_update(), session_key=request.session.session_key)
    item = get_object_or_404(ItemCarrito, pk=pk, carrito=carrito)
    item.delete()
    return redirect('ver_carrito')


@sensitive_post_parameters('dni')
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
            try:
                with transaction.atomic():
                    Carrito.objects.select_for_update().get(pk=carrito.pk)
                    product_ids = set(ItemCarrito.objects.filter(carrito=carrito).values_list('producto_id', flat=True))
                    links = Producto.objects.filter(pk__in=product_ids).values('tipo', 'parte_superior_id', 'parte_inferior_id')
                    component_ids = {pk for link in links if link['tipo'] == 'conjunto'
                                     for pk in (link['parte_superior_id'], link['parte_inferior_id']) if pk}
                    # One sorted lock pass avoids opposite lock orders in mixed carts.
                    lock_ids = product_ids | component_ids
                    locked_products = list(Producto.objects.select_for_update().filter(pk__in=lock_ids).order_by('pk'))
                    if any(p.tipo == 'conjunto' and not {p.parte_superior_id, p.parte_inferior_id} <= lock_ids
                           for p in locked_products if p.pk in product_ids):
                        raise ValidationError('La composición del conjunto cambió. Revisá tu carrito antes de confirmar.')
                    locked_items = list(ItemCarrito.objects.select_for_update(of=('self',)).select_related(
                        'producto', 'producto__parte_superior', 'producto__parte_inferior',
                        'color', 'talle__color', 'talle_inferior__color').filter(carrito=carrito).order_by('pk'))
                    if not locked_items:
                        raise ValidationError('Tu carrito está vacío. Volvé a elegir los productos.')
                    envio = OpcionEnvio.objects.select_for_update().filter(pk=envio.pk).first()
                    if not envio:
                        raise ValidationError('La opción de envío ya no está disponible. Elegí otra antes de confirmar.')
                    subtotal = sum(item.subtotal() for item in locked_items)
                    if codigo_obj:
                        codigo_obj = CodigoPromocional.objects.select_for_update().filter(pk=codigo_obj.pk).first()
                        if not codigo_obj or not codigo_obj.es_valido():
                            raise ValidationError('El código promocional ya no está disponible. Revisá el total antes de confirmar.')
                        descuento = codigo_obj.calcular_descuento(subtotal)
                    total_sin_recargo = subtotal - descuento + envio.costo
                    total = _total_mercadopago(total_sin_recargo) if metodo_pago == 'mercadopago' else total_sin_recargo
                    quantities = requirements(locked_items)
                    adjust_locked(quantities, -1)
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
                    orden.dni_hash = dni_digest(form.cleaned_data['dni'], orden.seguimiento_token)
                    orden.save(update_fields=['dni_hash'])

                    if codigo_obj:
                        codigo_obj.usos_actuales += 1
                        codigo_obj.save()

                    for item in locked_items:
                        details = {}
                        if item.producto.tipo == 'conjunto':
                            details = {
                                'detalle_superior': f'{item.producto.parte_superior.nombre} — {item.talle.color.nombre} — {item.talle.talle}',
                                'detalle_inferior': f'{item.producto.parte_inferior.nombre} — {item.talle_inferior.color.nombre} — {item.talle_inferior.talle}',
                            }
                        ItemOrden.objects.create(
                            orden=orden,
                            producto=item.producto,
                            cantidad=item.cantidad,
                            precio=item.producto.precio,
                            color=item.color,
                            talle=item.talle,
                            talle_inferior=item.talle_inferior,
                            nombre_historico=item.producto.nombre,
                            color_historico=item.color.nombre if item.color else '',
                            talle_historico=item.talle.talle if item.talle else '',
                            **details,
                        )

                    if metodo_pago != 'mercadopago':
                        queue_initial(orden)

                    items.delete()
                if codigo_obj:
                    request.session.pop('codigo_promo', None)
            except (ValidationError, OperationalError) as exc:
                form.add_error(None, exc if isinstance(exc, ValidationError) else
                               'No pudimos reservar el stock en este momento. Volvé a intentar.')
                return render(request, 'tienda/checkout.html', {
                    'form': form, 'items': items, 'subtotal': subtotal, 'descuento': descuento,
                    'total_con_descuento': subtotal - descuento, 'codigo_aplicado': codigo_aplicado,
                    'GOOGLE_MAPS_API_KEY': settings.GOOGLE_MAPS_API_KEY,
                })

            remember_checkout(request, orden)

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
    orden = Orden.objects.filter(pk=pk).first()
    if orden is None or not can_access_order(request, orden):
        return redirect('seguir_pedido')
    if orden.metodo_pago == 'mercadopago' and not orden.pagado:
        return render(request, 'tienda/pago_mp.html', {
            'orden': orden,
            'mp_url': reverse('pago_mp', args=[orden.pk]),
            'estado_pago': 'pendiente',
        })
    return render(request, 'tienda/confirmacion.html', {'orden': orden})


def confirmacion_transferencia(request, pk):
    orden = Orden.objects.filter(pk=pk).first()
    if orden is None or not can_access_order(request, orden):
        return redirect('seguir_pedido')
    return render(request, 'tienda/confirmacion_transferencia.html', {'orden': orden})


def pago_mp(request, pk):
    orden = Orden.objects.filter(pk=pk).first()
    if orden is None or not can_access_order(request, orden):
        return redirect('seguir_pedido')

    if orden.metodo_pago != 'mercadopago':
        return redirect('confirmacion', pk=orden.pk)
    if orden.pagado:
        return redirect('confirmacion', pk=orden.pk)

    sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
    envio_costo = orden.envio.costo if orden.envio else Decimal('0.00')
    productos_con_descuento = orden.subtotal - orden.descuento
    recargo = orden.total - productos_con_descuento - envio_costo

    preference_items = [{
        "id": f"orden-{orden.pk}-productos",
        "title": f"Productos Misso — pedido #{orden.pk}",
        "currency_id": "ARS",
        "quantity": 1,
        "unit_price": float(productos_con_descuento),
    }]
    if envio_costo > 0:
        preference_items.append({
            "id": f"orden-{orden.pk}-envio",
            "title": f"Envío — {orden.envio.nombre}",
            "currency_id": "ARS",
            "quantity": 1,
            "unit_price": float(envio_costo),
        })
    if recargo > 0:
        preference_items.append({
            "id": f"orden-{orden.pk}-recargo",
            "title": "Recargo Mercado Pago (10%)",
            "currency_id": "ARS",
            "quantity": 1,
            "unit_price": float(recargo),
        })

    site_url = settings.SITE_URL

    preference_data = {
        "items": preference_items,
        "payer": {"email": orden.email},
        "back_urls": {
            "success": f"{site_url}{reverse('mercadopago_retorno', args=[orden.pk])}",
            "failure": f"{site_url}{reverse('mercadopago_retorno', args=[orden.pk])}",
            "pending": f"{site_url}{reverse('mercadopago_retorno', args=[orden.pk])}",
        },
        "notification_url": f"{site_url}{reverse('mercadopago_webhook')}",
        "auto_return": "approved",
        "external_reference": str(orden.pk),
    }

    preference_response = sdk.preference().create(preference_data)
    preference = preference_response["response"]
    mp_url = preference.get("init_point")

    if not mp_url:
        return redirect('ver_carrito')

    return redirect(mp_url)


def _confirmar_pago_mercadopago(payment_id):
    """Confirma la orden solo con los datos obtenidos de la API de Mercado Pago."""
    if not str(payment_id).isascii() or not str(payment_id).isdigit() or len(str(payment_id)) > 100:
        return None
    sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
    payment_response = sdk.payment().get(str(payment_id))
    api_status = payment_response.get('status', 0)
    if api_status == 429 or (isinstance(api_status, int) and api_status >= 500):
        # The SDK returns HTTP failures as data rather than always raising.
        # Let the webhook return 503 so Mercado Pago retries the verification.
        raise RuntimeError('Mercado Pago no está disponible temporalmente.')
    if payment_response.get('status') != 200:
        return None

    payment = payment_response.get('response', {})
    if (str(payment.get('id')) != str(payment_id) or payment.get('status') != 'approved'
            or payment.get('currency_id') != 'ARS'):
        return None

    try:
        orden_pk = int(payment.get('external_reference'))
        monto_pagado = Decimal(str(payment.get('transaction_amount')))
    except (TypeError, ValueError, InvalidOperation):
        return None

    if not monto_pagado.is_finite():
        return None
    return confirm_verified_payment(orden_pk, str(payment_id), monto_pagado)


def mercadopago_retorno(request, pk):
    orden = Orden.objects.filter(pk=pk, metodo_pago='mercadopago').first()
    if orden is None or not can_access_order(request, orden):
        return redirect('seguir_pedido')
    payment_id = request.GET.get('payment_id') or request.GET.get('collection_id')
    orden_confirmada = None
    if payment_id:
        try:
            orden_confirmada = _confirmar_pago_mercadopago(payment_id)
        except Exception:
            orden_confirmada = None

    if orden_confirmada and orden_confirmada.pk == orden.pk:
        return redirect('confirmacion', pk=orden.pk)

    return render(request, 'tienda/pago_mp.html', {
        'orden': orden,
        'mp_url': reverse('pago_mp', args=[orden.pk]),
        'estado_pago': request.GET.get('status', 'pendiente'),
    })


@csrf_exempt
def mercadopago_webhook(request):
    if request.method != 'POST':
        return JsonResponse({'ok': True})

    try:
        payload = json.loads(request.body or b'{}')
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}

    if not isinstance(payload, dict):
        payload = {}
    data = payload.get('data') if isinstance(payload.get('data'), dict) else {}
    topic = request.GET.get('type') or payload.get('type')
    payment_id = request.GET.get('data.id') or data.get('id')
    if topic != 'payment' or not payment_id:
        return JsonResponse({'ok': True})

    try:
        _confirmar_pago_mercadopago(payment_id)
    except Exception:
        # Un error temporal provoca un reintento de la notificación.
        return JsonResponse({'ok': False}, status=503)
    return JsonResponse({'ok': True})
