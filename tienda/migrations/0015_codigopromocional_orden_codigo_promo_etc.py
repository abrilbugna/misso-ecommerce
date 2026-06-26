from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0014_remove_colorproducto_imagen_remove_producto_imagen_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='CodigoPromocional',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(max_length=50, unique=True)),
                ('descuento_porcentaje', models.DecimalField(blank=True, decimal_places=2, help_text='Ej: 15 para 15% de descuento', max_digits=5, null=True)),
                ('descuento_fijo', models.DecimalField(blank=True, decimal_places=2, help_text='Monto fijo en pesos', max_digits=10, null=True)),
                ('activo', models.BooleanField(default=True)),
                ('usos_maximos', models.PositiveIntegerField(blank=True, help_text='Dejar vacío para usos ilimitados', null=True)),
                ('usos_actuales', models.PositiveIntegerField(default=0)),
                ('fecha_expiracion', models.DateField(blank=True, help_text='Dejar vacío si no expira', null=True)),
            ],
            options={
                'verbose_name': 'Código promocional',
                'verbose_name_plural': 'Códigos promocionales',
            },
        ),
        migrations.AddField(
            model_name='orden',
            name='subtotal',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='orden',
            name='descuento',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name='orden',
            name='codigo_promo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='tienda.codigopromocional'),
        ),
    ]
