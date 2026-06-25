from django.contrib import admin
from django.conf import settings
import requests
from .models import Producto, Carrito, ItemCarrito, Orden, ItemOrden, OpcionEnvio, ColorProducto, TalleProducto

class TalleProductoInline(admin.TabularInline):
    model = TalleProducto
    extra = 4

class ColorProductoInline(admin.TabularInline):
    model = ColorProducto
    extra = 1
    show_change_link = True

class ItemOrdenInline(admin.TabularInline):
    model = ItemOrden
    extra = 0
    readonly_fields = ['producto', 'color', 'talle', 'cantidad', 'precio']
    can_delete = False

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
    fields = ['nombre', 'descripcion', 'precio', 'categoria', 'activo', 'destacado', 'imagen']
    inlines = [ColorProductoInline]

@admin.register(Carrito)
class CarritoAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'creado']

@admin.register(ItemCarrito)
class ItemCarritoAdmin(admin.ModelAdmin):
    list_display = ['carrito', 'producto', 'cantidad', 'color', 'talle']

def enviar_comprobante_cliente(orden):
    items = orden.itemorden_set.all()
    detalle_items = ""
    for item in items:
        color_txt = item.color.nombre if item.color else "Sin color"
        talle_txt = item.talle.talle if item.talle else "Sin talle"
        detalle_items += (
            f"- {item.producto.nombre} | Color: {color_txt} | Talle: {talle_txt} | Cant: {item.cantidad} | Precio: ${item.precio}\n"
        )

    cuerpo = (
        f"¡Hola {orden.nombre}! 🛍\n\n"
        f"Tu pedido #{orden.pk} fue confirmado. Acá está tu comprobante:\n\n"
        f"{detalle_items}\n"
        f"Envío: {orden.envio}\n"
        f"Método de pago: {orden.metodo_pago}\n"
        f"Total: ${orden.total}\n\n"
        f"¡Gracias por tu compra!\n\n"
        f"— Misso ♡"
    )

    requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": "Misso <hola@misso.ar>",
            "to": [orden.email],
            "subject": f"Tu pedido #{orden.pk} fue confirmado — Misso",
            "text": cuerpo,
        },
        timeout=5,
    )

@admin.register(Orden)
class OrdenAdmin(admin.ModelAdmin):
    list_display = ['pk', 'nombre', 'email', 'total', 'metodo_pago', 'estado', 'pagado', 'creado']
    list_filter = ['estado', 'metodo_pago', 'pagado']
    list_editable = ['estado', 'pagado']
    readonly_fields = ['nombre', 'email', 'telefono', 'direccion', 'total', 'envio', 'metodo_pago', 'creado']
    inlines = [ItemOrdenInline]

    def save_model(self, request, obj, form, change):
        if change and 'estado' in form.changed_data:
            anterior = Orden.objects.get(pk=obj.pk)

            if obj.estado == 'cancelado' and anterior.estado != 'cancelado':
                for item in obj.itemorden_set.all():
                    if item.talle:
                        item.talle.stock += item.cantidad
                        item.talle.save()

            elif anterior.estado == 'cancelado' and obj.estado == 'en_proceso':
                for item in obj.itemorden_set.all():
                    if item.talle:
                        item.talle.stock = max(0, item.talle.stock - item.cantidad)
                        item.talle.save()

            elif obj.estado == 'finalizado' and anterior.estado != 'finalizado':
                try:
                    enviar_comprobante_cliente(obj)
                except Exception as e:
                    self.message_user(request, f"Pedido guardado, pero hubo un error al enviar el mail: {e}", level='warning')

        super().save_model(request, obj, form, change)

@admin.register(OpcionEnvio)
class OpcionEnvioAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'costo', 'activo']
    list_editable = ['costo', 'activo']