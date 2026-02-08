# 将订单数量统一为基础单位
# 历史数据假定为显示单位，需转换为基础单位

from django.db import migrations
from inventory.services.unit_conversion import UnitConversionService


def convert_sales_order_item_quantity(apps, schema_editor):
    """SalesOrderItem.quantity: 显示单位 -> 基础单位"""
    SalesOrderItem = apps.get_model('sales', 'SalesOrderItem')
    Product = apps.get_model('inventory', 'Product')
    for item in SalesOrderItem.objects.select_related('product'):
        try:
            product = Product.objects.get(pk=item.product_id)
            if not product.display_unit_id:
                continue
            base_qty = UnitConversionService.from_display(product, item.quantity)
            if base_qty != item.quantity:
                item.quantity = base_qty
                item.save(update_fields=['quantity'])
        except Exception:
            pass


def convert_sales_order_item_batch_quantity(apps, schema_editor):
    """SalesOrderItemBatch.quantity: 显示单位 -> 基础单位"""
    SalesOrderItemBatch = apps.get_model('sales', 'SalesOrderItemBatch')
    SalesOrderItem = apps.get_model('sales', 'SalesOrderItem')
    Product = apps.get_model('inventory', 'Product')
    for ob in SalesOrderItemBatch.objects.select_related('order_item'):
        try:
            oi = SalesOrderItem.objects.get(pk=ob.order_item_id)
            product = Product.objects.get(pk=oi.product_id)
            if not product.display_unit_id:
                continue
            base_qty = UnitConversionService.from_display(product, ob.quantity)
            if base_qty != ob.quantity:
                ob.quantity = base_qty
                ob.save(update_fields=['quantity'])
        except Exception:
            pass


def noop_reverse(apps, schema_editor):
    """不可逆，回滚时不做任何事"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0012_change_reserve_inventory_to_lock_default'),
    ]

    operations = [
        migrations.RunPython(convert_sales_order_item_quantity, noop_reverse),
        migrations.RunPython(convert_sales_order_item_batch_quantity, noop_reverse),
    ]
