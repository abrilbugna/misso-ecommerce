"""Coordinated writes for the panel, without changing the public checkout."""
import hashlib
import json
from collections import Counter

import cloudinary
import cloudinary.uploader
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction

from .models import Producto, ColorProducto, TalleProducto, Orden
from .panel_forms import (ProductoForm, ColorFormSet, TalleFormSet, ImagenFormSet,
                          VideoFormSet, ConfirmChangesForm)


def fingerprint(product):
    if not product.pk:
        return 'new'
    data = [list(Producto.objects.filter(pk=product.pk).values()),
            list(product.colores.order_by('pk').values()),
            list(TalleProducto.objects.filter(color__producto=product).order_by('pk').values()),
            list(product.imagenes.order_by('pk').values()),
            list(product.videos.order_by('pk').values())]
    return hashlib.sha256(json.dumps(data, default=str, sort_keys=True).encode()).hexdigest()


def revision_for(product):
    return signing.dumps({'pk': product.pk, 'digest': fingerprint(product)}, salt='panel.product')


class ProductoEditor:
    def __init__(self, instance, data=None, files=None):
        self.instance = instance
        self.form = ProductoForm(data, instance=instance, prefix='producto')
        self.colors = ColorFormSet(data, instance=instance, prefix='colors')
        self.groups = []
        choices, refs = [], {}
        for color_form in self.colors:
            sizes = TalleFormSet(data, instance=color_form.instance, prefix=f'{color_form.prefix}-sizes')
            self.groups.append({'form': color_form, 'sizes': sizes, 'empty_sizes': not sizes.initial_form_count()})
            name = str(color_form['nombre'].value() or '').strip()
            if name:
                choices.append((color_form.prefix, name))
            if color_form.instance.pk:
                refs[color_form.instance.pk] = color_form.prefix
        self.images = ImagenFormSet(data, files, instance=instance, prefix='images', form_kwargs={'color_choices': choices, 'color_refs': refs})
        self.videos = VideoFormSet(data, files, instance=instance, prefix='videos')
        self.confirm = ConfirmChangesForm(data, initial={'revision': revision_for(instance)})
        self.empty_color = self.colors.empty_form
        self.empty_sizes = TalleFormSet(instance=ColorProducto(), prefix='colors-__prefix__-sizes')

    def is_valid(self):
        valid = [self.form.is_valid(), self.colors.is_valid(), self.images.is_valid(), self.videos.is_valid(), self.confirm.is_valid()]
        for group in self.groups:
            valid.append(group['sizes'].is_valid())
            if any(f.has_changed() for f in group['sizes']) and not group['form'].cleaned_data.get('nombre'):
                group['form'].add_error('nombre', 'Nombrá el color de estas variantes.')
                valid.append(False)
        if self.images.deleted_forms or self.videos.deleted_forms:
            if not self.confirm.cleaned_data.get('confirm_delete'):
                self.confirm.add_error('confirm_delete', 'Confirmá la eliminación de los archivos marcados.')
                valid.append(False)
        return all(valid)

    def check_permissions(self, user):
        action = 'change' if self.instance.pk else 'add'
        if not user.has_perm(f'tienda.{action}_producto'):
            raise PermissionDenied
        sets = [self.colors, self.images, self.videos, *(g['sizes'] for g in self.groups)]
        for formset in sets:
            for form in formset:
                if form.cleaned_data.get('DELETE') and form.instance.pk:
                    action = 'delete'
                elif form.has_changed():
                    action = 'change' if form.instance.pk else 'add'
                else:
                    continue
                if not user.has_perm(f'tienda.{action}_{formset.model._meta.model_name}'):
                    raise PermissionDenied

    @transaction.atomic
    def save(self, user):
        self.check_permissions(user)
        if self.instance.pk:
            Producto.objects.select_for_update().get(pk=self.instance.pk)
            list(TalleProducto.objects.select_for_update().filter(color__producto=self.instance).order_by('pk'))
        try:
            revision = signing.loads(self.confirm.cleaned_data['revision'], salt='panel.product')
        except signing.BadSignature:
            raise ValidationError('La ficha venció. Recargá antes de guardar.')
        if revision != {'pk': self.instance.pk, 'digest': fingerprint(self.instance)}:
            raise ValidationError('El producto o su stock cambió mientras editabas. Recargá la ficha para evitar sobrescribirlo.')
        product = self.form.save()
        saved_colors = {}
        for group in self.groups:
            form, sizes = group['form'], group['sizes']
            if not form.instance.pk and not form.has_changed():
                continue
            color = form.save(commit=False)
            color.producto = product
            color.save()
            saved_colors[form.prefix] = color
            sizes.instance = color
            sizes.save()
        for formset, field, kind in [(self.images, 'imagen', 'image'), (self.videos, 'video', 'video')]:
            for form in formset:
                if form.cleaned_data.get('DELETE'):
                    if form.instance.pk:
                        form.instance.delete()  # Never delete Cloudinary originals/history remotely.
                    continue
                if not form.has_changed():
                    continue
                obj = form.save(commit=False)
                obj.producto = product
                if kind == 'image':
                    obj.color = saved_colors.get(form.cleaned_data.get('color_ref'))
                upload = form.cleaned_data.get(field)
                if isinstance(upload, UploadedFile):
                    result = cloudinary.uploader.upload(upload, resource_type=kind)
                    setattr(obj, field, cloudinary.CloudinaryResource(
                        public_id=result['public_id'], format=result.get('format'),
                        version=result.get('version'), resource_type=kind, type=result.get('type', 'upload')))
                obj.save()
        return product


def order_revision(order):
    return signing.dumps({'pk': order.pk, 'estado': order.estado, 'pagado': order.pagado}, salt='panel.order')


@transaction.atomic
def update_order(pk, cleaned):
    order = Orden.objects.select_for_update().get(pk=pk)
    try:
        old = signing.loads(cleaned['revision'], salt='panel.order')
    except signing.BadSignature:
        raise ValidationError('La ficha venció. Recargá el pedido.')
    if old != {'pk': order.pk, 'estado': order.estado, 'pagado': order.pagado}:
        raise ValidationError('El pedido cambió mientras lo editabas. Recargá antes de guardar.')
    new_state = cleaned['estado']
    delta = (1 if new_state == 'cancelado' else -1) if (order.estado == 'cancelado') != (new_state == 'cancelado') else 0
    if delta:
        quantities = Counter()
        for item in order.itemorden_set.all():
            if item.talle_id:
                if item.cantidad <= 0:
                    raise ValidationError('El pedido tiene cantidades inválidas. Revisalo desde el panel técnico.')
                quantities[item.talle_id] += item.cantidad
        for size in TalleProducto.objects.select_for_update().filter(pk__in=quantities).order_by('pk'):
            stock = size.stock + delta * quantities[size.pk]
            if stock < 0:
                raise ValidationError(f'No hay stock suficiente para reactivar {size.color.nombre}, talle {size.talle}.')
            size.stock = stock
            size.save(update_fields=['stock'])
    order.estado = new_state
    order.pagado = cleaned['pagado']
    order.save(update_fields=['estado', 'pagado'])
    return order
