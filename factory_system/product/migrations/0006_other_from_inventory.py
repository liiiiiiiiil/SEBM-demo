# 将库存中「其它」类型物品迁移为产品主数据（product.Product category=other）并关联
from django.db import migrations


def other_inventory_to_master(apps, schema_editor):
    Inventory = apps.get_model('inventory', 'Inventory')
    Product = apps.get_model('product', 'Product')
    Unit = apps.get_model('inventory', 'Unit')
    default_unit = Unit.objects.filter(is_active=True).first()
    if not default_unit:
        return
    for inv in Inventory.objects.filter(inventory_type='other', product_master__isnull=True):
        name = (inv.other_name or '').strip() or f"其它-{inv.pk}"
        sku = f"OTH-{inv.pk}"
        if Product.objects.filter(sku=sku).exists():
            continue
        base_unit = inv.other_unit if inv.other_unit_id else default_unit
        master = Product.objects.create(
            sku=sku,
            name=name,
            category='other',
            unit_price=inv.other_unit_price or 0,
            base_unit=base_unit,
            display_unit=base_unit,
            safety_stock=0,
        )
        inv.product_master_id = master.id
        inv.save(update_fields=['product_master_id'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('product', '0005_item_conversion_master_product'),
        ('inventory', '0029_fill_inventory_product_master'),
    ]
    operations = [migrations.RunPython(other_inventory_to_master, noop)]
