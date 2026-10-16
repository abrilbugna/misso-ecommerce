from django.contrib import admin
from .models import Producto, Carrito, ItemCarrito, Orden, ItemOrden, OpcionEnvio, ColorProducto, TalleProducto, ImagenProducto, VideoProducto, CodigoPromocional, NewsletterContacto
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html
from .panel_forms import OrdenForm
from .order_services import update_order

class TalleProductoInline(admin.TabularInline):
    model = TalleProducto
    extra = 4
    fields = ['talle', 'stock']

class ColorProductoInline(admin.TabularInline):
    model = ColorProducto
    extra = 1
    fields = ['nombre']
    show_change_link = True

class ImagenProductoInline(admin.TabularInline):
    model = ImagenProducto
    extra = 1
    fields = ['imagen', 'color', 'orden']

class VideoProductoInline(admin.TabularInline):
    model = VideoProducto
    extra = 1
    fields = ['video', 'orden']

class ItemOrdenInline(admin.TabularInline):
    model = ItemOrden
    extra = 0
    readonly_fields = ['producto', 'color', 'talle', 'cantidad', 'precio']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(ColorProducto)
class ColorProductoAdmin(admin.ModelAdmin):
    list_display = ['producto', 'nombre']
    list_filter = ['producto']
    inlines = [TalleProductoInline]

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'precio', 'activo', 'destacado', 'categoria']
    list_editable = ['precio', 'activo', 'destacado']
    search_fields = ['nombre']
    list_filter = ['categoria', 'activo', 'destacado']
    fields = ['nombre', 'descripcion', 'precio', 'categoria', 'activo', 'destacado']
    inlines = [ColorProductoInline, ImagenProductoInline, VideoProductoInline]

@admin.register(Carrito)
class CarritoAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'creado']

@admin.register(ItemCarrito)
class ItemCarritoAdmin(admin.ModelAdmin):
    list_display = ['carrito', 'producto', 'cantidad', 'color', 'talle']

@admin.register(CodigoPromocional)
class CodigoPromocionalAdmin(admin.ModelAdmin):
    list_display = ['codigo', 'descuento_porcentaje', 'descuento_fijo', 'activo', 'usos_actuales', 'usos_maximos', 'fecha_expiracion']
    list_editable = ['activo']
    search_fields = ['codigo']
    fields = ['codigo', 'descuento_porcentaje', 'descuento_fijo', 'activo', 'usos_maximos', 'usos_actuales', 'fecha_expiracion']
    readonly_fields = ['usos_actuales']


@admin.register(NewsletterContacto)
class NewsletterContactoAdmin(admin.ModelAdmin):
    list_display = ['email', 'activo', 'codigo_promocional', 'consentimiento_comercial', 'consentimiento_fecha', 'creado']
    list_editable = ['activo']
    list_filter = ['activo', 'consentimiento_comercial']
    search_fields = ['email']
    readonly_fields = ['email', 'codigo_promocional', 'consentimiento_comercial', 'consentimiento_fecha', 'creado']

    def has_add_permission(self, request):
        return False

@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    form = OrdenForm
    list_display = ['pk', 'nombre', 'total', 'metodo_pago', 'estado', 'pagado', 'pago_origen', 'codigo_seguimiento', 'creado']
    list_filter = ['estado', 'metodo_pago', 'pagado']
    readonly_fields = ['nombre', 'email', 'telefono', 'direccion', 'subtotal', 'descuento', 'codigo_promo', 'total', 'envio', 'metodo_pago', 'creado', 'pago_origen', 'pago_confirmado_at', 'mp_payment_id', 'despachado_at', 'entregado_at', 'finalizado_historico', 'gestion_notificaciones']
    fields = [*readonly_fields, 'estado', 'pagado', 'transportista', 'codigo_seguimiento', 'plazo_dias_habiles', 'confirmar', 'revision']
    inlines = [ItemOrdenInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Notificaciones')
    def gestion_notificaciones(self, obj):
        return format_html('<a href="{}">Gestionar correos en el panel de MISSO</a>', reverse('panel:pedido_editar', args=[obj.pk]))

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        # Lock before validation so a concurrent change becomes a normal form
        # error, not a save_model exception after the form was accepted.
        with transaction.atomic():
            if request.method == 'POST' and object_id and object_id.isdecimal():
                Orden.objects.select_for_update().filter(pk=int(object_id)).first()
            return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        saved = update_order(obj.pk, form.cleaned_data)
        obj.__dict__.update(saved.__dict__)

@admin.register(OpcionEnvio)
class OpcionEnvioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'costo', 'activo']
    list_editable = ['costo', 'activo']

# Subscription state is exclusively reconciled with Mercado Pago, even in /admin/.
from .models import Suscripcion, PagoSuscripcion, EventoMercadoPago, EmailSuscripcion


class SubscriptionReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Suscripcion)
class SuscripcionAdmin(SubscriptionReadOnlyAdmin):
    list_display = ('id', 'nombre', 'email', 'estado', 'importe', 'mp_preapproval_id', 'actualizado')
    list_filter = ('estado', 'creado')
    search_fields = ('nombre', 'email', 'telefono', 'external_reference', 'mp_preapproval_id')


@admin.register(EventoMercadoPago)
class EventoSuscripcionAdmin(SubscriptionReadOnlyAdmin):
    list_display = ('id', 'topico', 'recurso_id', 'recibido_at', 'procesado_at', 'intentos', 'error')
    list_filter = ('topico', 'procesado_at')


@admin.register(EmailSuscripcion)
class EmailSuscripcionAdmin(SubscriptionReadOnlyAdmin):
    list_display = ('id', 'suscripcion', 'tipo', 'enviado_at', 'intentos', 'revision_manual', 'error')
    exclude = ('payload',)


admin.site.register(PagoSuscripcion, SubscriptionReadOnlyAdmin)
