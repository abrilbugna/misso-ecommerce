from django.db import migrations


def backfill(apps, schema_editor):
    ItemOrden = apps.get_model('tienda', 'ItemOrden')
    batch = []
    for item in ItemOrden.objects.using(schema_editor.connection.alias).select_related('producto', 'color', 'talle').iterator(chunk_size=500):
        item.nombre_historico = item.producto.nombre
        item.color_historico = item.color.nombre if item.color_id else ''
        item.talle_historico = item.talle.talle if item.talle_id else ''
        batch.append(item)
        if len(batch) == 500:
            ItemOrden.objects.using(schema_editor.connection.alias).bulk_update(
                batch, ['nombre_historico', 'color_historico', 'talle_historico'])
            batch = []
    if batch:
        ItemOrden.objects.using(schema_editor.connection.alias).bulk_update(
            batch, ['nombre_historico', 'color_historico', 'talle_historico'])


class Migration(migrations.Migration):
    dependencies = [('tienda', '0023_itemorden_color_historico_itemorden_talle_historico_and_more')]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
