from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('tienda', '0009_remove_producto_imagen'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='colorproducto',
            name='stock',
        ),
        migrations.CreateModel(
            name='TalleProducto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('talle', models.CharField(choices=[('85', '85'), ('90', '90'), ('95', '95'), ('100', '100')], max_length=10)),
                ('stock', models.IntegerField(default=0)),
                ('color', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='talles', to='tienda.colorproducto')),
            ],
            options={
                'unique_together': {('color', 'talle')},
            },
        ),
        migrations.AddField(
            model_name='itemcarrito',
            name='talle',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='tienda.talleproducto'),
        ),
    ]