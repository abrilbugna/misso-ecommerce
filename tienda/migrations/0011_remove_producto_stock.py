from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0010_talleproducto_itemcarrito_talle'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='producto',
            name='stock',
        ),
    ]
