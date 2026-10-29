from decimal import Decimal
import logging

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST, require_http_methods

from .models import Producto, TalleProducto, Orden, CodigoPromocional, OpcionEnvio
from .panel_access import panel_required
from .panel_forms import (PanelLoginForm, LOW_STOCK_LIMIT, ProductoFilterForm, OrdenFilterForm,
                          OrdenForm, PromocionForm, EnvioForm)
from .panel_services import ProductoEditor, order_revision, update_order
from .panel_forms import OrderEmailActionForm
from .order_emails import request_order_email

logger = logging.getLogger(__name__)


class PanelLoginView(LoginView):
    template_name = 'panel/login.html'
    authentication_form = PanelLoginForm
    next_page = reverse_lazy('panel:inicio')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if not request.user.is_active or not request.user.is_staff:
                raise PermissionDenied
            return redirect('panel:inicio')
        return super().dispatch(request, *args, **kwargs)


@panel_required()
@require_POST
def cerrar_sesion(request):
    logout(request)
    return redirect('panel:login')


def page_context(request, queryset):
    query = request.GET.copy()
    query.pop('page', None)
    return {'page': Paginator(queryset, 24).get_page(request.GET.get('page')), 'query': query.urlencode()}


@panel_required()
def inicio(request):
    context = {'section': 'inicio', 'low_limit': LOW_STOCK_LIMIT}
    if request.user.has_perm('tienda.view_producto'):
        context['products'] = Producto.objects.aggregate(total=Count('id'), active=Count('id', filter=Q(activo=True)), inactive=Count('id', filter=Q(activo=False)))
    if request.user.has_perm('tienda.view_talleproducto'):
        context['stock'] = TalleProducto.objects.aggregate(zero=Count('id', filter=Q(stock=0)), low=Count('id', filter=Q(stock__gt=0, stock__lte=LOW_STOCK_LIMIT)))
    if request.user.has_perm('tienda.view_orden'):
        context['orders'] = Orden.objects.aggregate(pending=Count('id', filter=Q(estado='en_proceso')), unpaid=Count('id', filter=Q(pagado=False) & ~Q(estado='cancelado')))
        context['sales'] = Orden.objects.filter(pagado=True).exclude(estado='cancelado').aggregate(amount=Sum('total'))['amount'] or Decimal('0.00')
        context['recent_orders'] = Orden.objects.order_by('-creado')[:5]
    return render(request, 'panel/dashboard.html', context)


@panel_required('tienda.view_producto')
def productos(request):
    form = ProductoFilterForm(request.GET)
    products = Producto.objects.select_related('parte_superior', 'parte_inferior').prefetch_related(
        'imagenes', 'colores__talles', 'parte_superior__colores__talles', 'parte_inferior__colores__talles').order_by('-creado')
    if form.is_valid():
        data = form.cleaned_data
        if data['q']:
            products = products.filter(nombre__icontains=data['q'])
        for key in ('activo', 'destacado'):
            if data[key]:
                products = products.filter(**{key: data[key] == '1'})
        if data['categoria']:
            products = products.filter(categoria=data['categoria'])
        stock = data['stock']
    else:
        products = products.none()
        stock = ''
    product_list = list(products.distinct())
    for product in product_list:
        colors = list(product.colores.all())
        sizes = [size for color in colors for size in color.talles.all()]
        product.panel_stock = sum(size.stock for size in sizes)
        product.panel_colors = len(colors)
        product.panel_variants = len(sizes)
        if product.tipo == 'conjunto' and product.parte_superior_id and product.parte_inferior_id:
            top = {c.nombre.casefold(): sum(s.stock for s in c.talles.all()) for c in product.parte_superior.colores.all()}
            bottom = {c.nombre.casefold(): sum(s.stock for s in c.talles.all()) for c in product.parte_inferior.colores.all()}
            product.panel_stock = sum(min(count, bottom.get(name, 0)) for name, count in top.items())
            product.panel_colors = len(top.keys() & bottom.keys())
            product.panel_variants = 0
        product.panel_image = next(iter(product.imagenes.all()), None)
    if stock:
        product_list = [p for p in product_list if (
            (stock == 'zero' and p.panel_colors and p.panel_stock == 0)
            or (stock == 'low' and 0 < p.panel_stock <= LOW_STOCK_LIMIT)
            or (stock == 'available' and p.panel_stock > 0)
            or (stock == 'unconfigured' and not p.panel_colors))]
    context = page_context(request, product_list)
    return render(request, 'panel/productos.html', {**context, 'filter_form': form, 'section': 'productos'})


@panel_required()
@require_http_methods(['GET', 'POST'])
def producto_editar(request, pk=None):
    permission = 'change_producto' if pk else 'add_producto'
    if not request.user.has_perm(f'tienda.{permission}'):
        raise PermissionDenied
    product = get_object_or_404(Producto, pk=pk) if pk else Producto()
    editor = ProductoEditor(product, request.POST if request.method == 'POST' else None, request.FILES if request.method == 'POST' else None)
    if request.method == 'POST':
        if editor.is_valid():
            try:
                saved = editor.save(request.user)
            except PermissionDenied:
                raise
            except ValidationError as exc:
                editor.form.add_error(None, exc)
            except Exception:
                # Remote media uploads cannot be rolled back, but every DB write is atomic.
                logger.exception('No se pudo guardar un producto desde el panel')
                editor.form.add_error(None, 'No pudimos guardar los cambios. Revisá la conexión y volvé a seleccionar los archivos antes de reintentar.')
            else:
                messages.success(request, 'Producto actualizado' if pk else 'Producto creado')
                return redirect('panel:producto_editar', pk=saved.pk)
        messages.error(request, 'Revisá estos campos. No guardamos los cambios.')
    return render(request, 'panel/producto_form.html', {'editor': editor, 'product': product, 'section': 'productos', 'low_limit': LOW_STOCK_LIMIT})


@panel_required('tienda.view_orden')
def pedidos(request):
    form = OrdenFilterForm(request.GET)
    orders = Orden.objects.select_related('envio').prefetch_related('itemorden_set__producto').order_by('-creado')
    if form.is_valid():
        data = form.cleaned_data
        if data['q']:
            q = data['q'].lstrip('#')
            match = Q(nombre__icontains=q) | Q(email__icontains=q) | Q(telefono__icontains=q)
            if q.isascii() and q.isdecimal() and len(q) <= 18:
                match |= Q(pk=int(q))
            orders = orders.filter(match)
        for key in ('estado', 'metodo_pago'):
            if data[key]:
                orders = orders.filter(**{key: data[key]})
        if data['pagado']:
            orders = orders.filter(pagado=data['pagado'] == '1')
            if data['pagado'] == '0' and not data['estado']:
                orders = orders.exclude(estado='cancelado')
        if data['desde']:
            orders = orders.filter(creado__date__gte=data['desde'])
        if data['hasta']:
            orders = orders.filter(creado__date__lte=data['hasta'])
    else:
        orders = orders.none()
    return render(request, 'panel/pedidos.html', {**page_context(request, orders), 'filter_form': form, 'section': 'pedidos'})


@panel_required('tienda.view_orden')
@require_http_methods(['GET', 'POST'])
def pedido_editar(request, pk):
    order = get_object_or_404(Orden.objects.select_related('envio', 'codigo_promo').prefetch_related('itemorden_set__producto', 'itemorden_set__color', 'itemorden_set__talle'), pk=pk)
    form = OrdenForm(request.POST if request.method == 'POST' else None, instance=order, initial={'revision': order_revision(order)})
    if request.method == 'POST':
        if not request.user.has_perm('tienda.change_orden'):
            raise PermissionDenied
        if form.is_valid():
            try:
                saved = update_order(pk, form.cleaned_data)
            except ValidationError as exc:
                form.add_error(None, exc)
            except DatabaseError:
                form.add_error(None, 'No pudimos actualizar el pedido. Volvé a intentarlo.')
            else:
                messages.success(request, 'Pedido actualizado')
                return redirect('panel:pedido_editar', pk=pk)
        messages.error(request, 'No pudimos guardar los cambios. Revisá el formulario.')
    if request.method == 'POST':
        order.refresh_from_db()  # ModelForm validation must not display unsaved state as fact.
    emails = list(order.emails.all())
    latest = {email.tipo: email.pk for email in emails}
    for email in emails:
        email.is_latest = latest[email.tipo] == email.pk
    return render(request, 'panel/pedido_form.html', {'order': order, 'form': form, 'section': 'pedidos', 'emails': emails, 'email_revision': order_revision(order)})


@panel_required('tienda.view_orden', 'tienda.change_orden')
@require_http_methods(['POST'])
def pedido_email(request, pk):
    get_object_or_404(Orden, pk=pk)
    form = OrderEmailActionForm(request.POST)
    if form.is_valid():
        try:
            request_order_email(pk, form.cleaned_data['email_id'], form.cleaned_data['revision'], form.cleaned_data['action'])
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
        else:
            messages.success(request, 'Solicitud registrada. Consultá el estado de la notificación más abajo.')
    else:
        messages.error(request, 'Confirmá explícitamente la acción de correo.')
    return redirect('panel:pedido_editar', pk=pk)


@panel_required('tienda.view_codigopromocional')
def promociones(request):
    return render(request, 'panel/promociones.html', {**page_context(request, CodigoPromocional.objects.order_by('codigo')), 'section': 'promociones'})


@panel_required('tienda.view_opcionenvio')
def envios(request):
    return render(request, 'panel/envios.html', {**page_context(request, OpcionEnvio.objects.order_by('nombre')), 'section': 'envios'})


def simple_edit(request, pk, model, form_class, section, singular):
    action = 'change' if pk else 'add'
    if not request.user.has_perm(f'tienda.{action}_{model._meta.model_name}'):
        raise PermissionDenied
    obj = get_object_or_404(model, pk=pk) if pk else model()
    form = form_class(request.POST if request.method == 'POST' else None, instance=obj)
    if request.method == 'POST':
        if form.is_valid():
            try:
                form.save()
            except DatabaseError:
                form.add_error(None, 'No pudimos guardar los cambios. Volvé a intentarlo.')
            else:
                messages.success(request, f'{singular} guardado')
                return redirect(f'panel:{section}')
        messages.error(request, 'Revisá estos campos. No guardamos los cambios.')
    return render(request, 'panel/simple_form.html', {'form': form, 'object': obj, 'section': section, 'singular': singular})


@panel_required()
@require_http_methods(['GET', 'POST'])
def promocion_editar(request, pk=None):
    return simple_edit(request, pk, CodigoPromocional, PromocionForm, 'promociones', 'Código promocional')


@panel_required()
@require_http_methods(['GET', 'POST'])
def envio_editar(request, pk=None):
    return simple_edit(request, pk, OpcionEnvio, EnvioForm, 'envios', 'Envío')
