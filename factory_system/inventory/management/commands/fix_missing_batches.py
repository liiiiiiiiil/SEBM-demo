"""
修复库存数据：为有库存量但无批次记录的库存条目创建初始批次。

背景：初始化数据时直接设置了 Inventory.quantity 但未创建 Batch 记录，
导致扣减逻辑（按批次 FIFO 扣减）无法正常工作。
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from inventory.models import Inventory, Batch


class Command(BaseCommand):
    help = '为有库存但无批次的库存记录补建初始批次'

    def handle(self, *args, **options):
        with transaction.atomic():
            fixed = 0
            for inv in Inventory.objects.all():
                if inv.quantity <= 0:
                    continue

                batch_total = Batch.objects.filter(inventory=inv).aggregate(
                    total=__import__('django.db.models', fromlist=['Sum']).Sum('quantity')
                )['total'] or Decimal('0')

                missing = inv.quantity - batch_total
                if missing <= 0:
                    continue

                # 获取物品名称
                if inv.inventory_type == 'product' and inv.product:
                    item_name = inv.product.name
                    sku = inv.product.sku
                elif inv.inventory_type == 'material' and inv.material:
                    item_name = inv.material.name
                    sku = inv.material.sku
                else:
                    item_name = inv.other_name or '其它'
                    sku = 'OTHER'

                batch_no = f"{sku}-INIT-{timezone.now().strftime('%Y%m%d')}"
                batch = Batch.objects.create(
                    batch_no=batch_no,
                    inventory=inv,
                    batch_date=timezone.now().date(),
                    quantity=missing,
                    unit_price=None,
                    remark='系统自动补建初始批次（修复缺失批次数据）',
                )

                self.stdout.write(
                    self.style.SUCCESS(
                        f'  ✓ {inv.get_inventory_type_display()} {item_name}: '
                        f'补建批次 {batch_no}，数量 {missing}'
                    )
                )
                fixed += 1

            self.stdout.write('')
            if fixed:
                self.stdout.write(self.style.SUCCESS(f'共修复 {fixed} 条库存记录'))
            else:
                self.stdout.write('所有库存记录的批次数据均正常，无需修复')
