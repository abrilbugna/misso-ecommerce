from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0011_remove_producto_stock'),
    ]

    operations = [
        migrations.AddField(
            model_name='producto',
            name='imagen',
            field=models.ImageField(blank=True, null=True, upload_to='productos/sin_variante/'),
        ),
    ]