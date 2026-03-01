# 产品主数据关联：inventory 的 Product/Material 指向 product.Product（字典源）
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0024_add_other_unit_price'),
        ('product', '0002_product_models'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='master_product',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_product',
                to='product.product',
                verbose_name='产品主数据',
            ),
        ),
        migrations.AddField(
            model_name='material',
            name='master_product',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='inventory_material',
                to='product.product',
                verbose_name='产品主数据',
            ),
        ),
    ]
