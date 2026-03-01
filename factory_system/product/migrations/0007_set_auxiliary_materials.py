# 参考库存管理：将减水剂、增稠剂、早强剂、缓凝剂、阻燃剂设为辅料（product.Product + inventory.Material）
from django.db import migrations

# 与 init_building_materials_data 中 material_type='auxiliary' 的 SKU 一致
AUXILIARY_SKUS = ('MAT-101', 'MAT-102', 'MAT-103', 'MAT-104', 'MAT-302')


def set_auxiliary_materials(apps, schema_editor):
    Product = apps.get_model('product', 'Product')
    Material = apps.get_model('inventory', 'Material')

    Product.objects.filter(sku__in=AUXILIARY_SKUS).update(category='auxiliary')
    Material.objects.filter(sku__in=AUXILIARY_SKUS).update(material_type='auxiliary')


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0006_other_from_inventory'),
        ('inventory', '0025_product_material_master_product'),
    ]

    operations = [
        migrations.RunPython(set_auxiliary_materials, noop_reverse),
    ]
