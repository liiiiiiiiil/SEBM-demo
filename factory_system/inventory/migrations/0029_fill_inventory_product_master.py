# 为 Inventory 回填 product_master（从 product.master_product / material.master_product）
from django.db import migrations


def fill_product_master(apps, schema_editor):
    Inventory = apps.get_model('inventory', 'Inventory')
    for inv in Inventory.objects.all():
        if inv.inventory_type == 'product' and inv.product_id and inv.product.master_product_id:
            inv.product_master_id = inv.product.master_product_id
            inv.save(update_fields=['product_master_id'])
        elif inv.inventory_type == 'material' and inv.material_id and inv.material.master_product_id:
            inv.product_master_id = inv.material.master_product_id
            inv.save(update_fields=['product_master_id'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('inventory', '0028_inventory_product_master')]
    operations = [migrations.RunPython(fill_product_master, noop)]
