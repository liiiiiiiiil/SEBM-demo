# 从 inventory.Product / Material / BOM 迁移数据到 product.Product 与 product.BOM，并回写 master_product
from django.db import migrations


def copy_inventory_to_product(apps, schema_editor):
    InventoryProduct = apps.get_model('inventory', 'Product')
    InventoryMaterial = apps.get_model('inventory', 'Material')
    InventoryBOM = apps.get_model('inventory', 'BOM')
    ProductProduct = apps.get_model('product', 'Product')
    ProductBOM = apps.get_model('product', 'BOM')

    # 1) 成品 -> product.Product (finished)
    for inv_p in InventoryProduct.objects.select_related('base_unit', 'display_unit').all():
        master, _ = ProductProduct.objects.get_or_create(
            sku=inv_p.sku,
            defaults={
                'name': inv_p.name,
                'category': 'finished',
                'unit_price': inv_p.unit_price or 0,
                'base_unit_id': inv_p.base_unit_id,
                'display_unit_id': inv_p.display_unit_id or inv_p.base_unit_id,
                'specification': getattr(inv_p, 'specification', '') or '',
                'sale_price': getattr(inv_p, 'sale_price', None),
                'safety_stock': getattr(inv_p, 'safety_stock', 0) or 0,
            },
        )
        if master.name != inv_p.name or master.unit_price != (inv_p.unit_price or 0):
            master.name = inv_p.name
            master.unit_price = inv_p.unit_price or 0
            master.base_unit_id = inv_p.base_unit_id
            master.display_unit_id = inv_p.display_unit_id or inv_p.base_unit_id
            master.specification = getattr(inv_p, 'specification', '') or ''
            master.sale_price = getattr(inv_p, 'sale_price', None)
            master.safety_stock = getattr(inv_p, 'safety_stock', 0) or 0
            master.save()
        inv_p.master_product_id = master.id
        inv_p.save(update_fields=['master_product_id'])

    # 2) 原料 -> product.Product (raw)
    for inv_m in InventoryMaterial.objects.select_related('base_unit', 'display_unit').all():
        master, _ = ProductProduct.objects.get_or_create(
            sku=inv_m.sku,
            defaults={
                'name': inv_m.name,
                'category': 'raw',
                'unit_price': inv_m.unit_price or 0,
                'base_unit_id': inv_m.base_unit_id,
                'display_unit_id': inv_m.display_unit_id or inv_m.base_unit_id,
                'specification': '',
                'sale_price': None,
                'safety_stock': getattr(inv_m, 'safety_stock', 0) or 0,
            },
        )
        if master.name != inv_m.name or master.unit_price != (inv_m.unit_price or 0):
            master.name = inv_m.name
            master.unit_price = inv_m.unit_price or 0
            master.base_unit_id = inv_m.base_unit_id
            master.display_unit_id = inv_m.display_unit_id or inv_m.base_unit_id
            master.safety_stock = getattr(inv_m, 'safety_stock', 0) or 0
            master.save()
        inv_m.master_product_id = master.id
        inv_m.save(update_fields=['master_product_id'])

    # 3) inventory.BOM -> product.BOM（通过 master_product 映射）
    for inv_bom in InventoryBOM.objects.select_related('product', 'material', 'unit').all():
        if not inv_bom.product_id or not inv_bom.material_id:
            continue
        inv_p = InventoryProduct.objects.filter(pk=inv_bom.product_id).first()
        inv_m = InventoryMaterial.objects.filter(pk=inv_bom.material_id).first()
        if not inv_p or not inv_p.master_product_id or not inv_m or not inv_m.master_product_id:
            continue
        ProductBOM.objects.get_or_create(
            product_id=inv_p.master_product_id,
            component_id=inv_m.master_product_id,
            defaults={
                'quantity': inv_bom.quantity,
                'unit_id': inv_bom.unit_id,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0002_product_models'),
        ('inventory', '0025_product_material_master_product'),
    ]

    operations = [
        migrations.RunPython(copy_inventory_to_product, noop_reverse),
    ]
