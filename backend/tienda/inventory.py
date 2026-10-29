"""Physical inventory shared by individual products and sets."""
from collections import Counter

from django.core.exceptions import ValidationError

from .models import TalleProducto


def item_variants(item):
    if not item.producto.activo:
        raise ValidationError('Uno de los productos ya no está disponible. Revisá tu carrito.')
    if item.producto.tipo == 'conjunto':
        if not item.talle_id or not item.talle_inferior_id:
            raise ValidationError('Elegí los talles de ambas prendas del conjunto.')
        top, bottom = item.talle, item.talle_inferior
        if (top.color.producto_id != item.producto.parte_superior_id
                or bottom.color.producto_id != item.producto.parte_inferior_id
                or item.color_id != top.color_id
                or top.color.nombre.casefold() != bottom.color.nombre.casefold()):
            raise ValidationError('La combinación de prendas ya no está disponible. Volvé a elegir color y talles.')
        return (top, bottom)
    if item.talle_inferior_id:
        raise ValidationError('Esta prenda tiene una selección de talle inválida.')
    if item.talle_id:
        if item.talle.color.producto_id != item.producto_id or item.color_id != item.talle.color_id:
            raise ValidationError('El talle seleccionado no pertenece a esta prenda.')
        return (item.talle,)
    if item.producto.colores.exists():
        raise ValidationError('Elegí un color y un talle para esta prenda.')
    return ()


def requirements(items):
    quantities = Counter()
    for item in items:
        if item.cantidad < 1 or item.cantidad > 99:
            raise ValidationError('La cantidad de un producto no es válida.')
        for variant in item_variants(item):
            quantities[variant.pk] += item.cantidad
    return quantities


def adjust_locked(quantities, direction):
    """Call inside transaction.atomic. PostgreSQL locks rows in stable order."""
    variants = {v.pk: v for v in TalleProducto.objects.select_for_update(of=('self',)).select_related('color').filter(pk__in=quantities).order_by('pk')}
    if len(variants) != len(quantities):
        raise ValidationError('Una variante ya no está disponible. Revisá tu carrito.')
    for pk, count in quantities.items():
        variant = variants[pk]
        if direction < 0 and variant.stock < count:
            raise ValidationError(f'No hay stock suficiente de {variant.color.producto.nombre}, color {variant.color.nombre}, talle {variant.talle}. Revisá tu carrito.')
    for pk, count in quantities.items():
        variant = variants[pk]
        variant.stock += direction * count
        variant.save(update_fields=['stock'])
