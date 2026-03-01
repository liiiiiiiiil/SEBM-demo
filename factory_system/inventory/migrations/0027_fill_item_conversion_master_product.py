# 为 ItemUnitConversion 回填 master_product（从 product.master_product / material.master_product）
from django.db import migrations


def fill_master_product(apps, schema_editor):
    ItemUnitConversion = apps.get_model('inventory', 'ItemUnitConversion')
    for conv in ItemUnitConversion.objects.all():
        if conv.content_type == 'product' and conv.product_id and conv.product.master_product_id:
            conv.master_product_id = conv.product.master_product_id
            conv.save(update_fields=['master_product_id'])
        elif conv.content_type == 'material' and conv.material_id and conv.material.master_product_id:
            conv.master_product_id = conv.material.master_product_id
            conv.save(update_fields=['master_product_id'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('inventory', '0026_item_conversion_master_product')]
    operations = [migrations.RunPython(fill_master_product, noop)]
