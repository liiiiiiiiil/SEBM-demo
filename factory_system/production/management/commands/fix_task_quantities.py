"""修复生产任务中 required_quantity / completed_quantity 未按基础单位存储的问题。

背景：stock_task_create 以前直接将用户按显示单位输入的数量存入了
required_quantity 字段（应为基础单位），导致例如用户输入 3 吨 → 存为 3，
而 BOM 计算按 3 千克处理，实际应为 3000 千克。

本命令会：
1. 扫描所有 display_unit ≠ base_unit 的任务
2. 判断该任务 required_quantity 是否可能是显示单位值
   （判据：值 < factor，即"如果当成基础单位来看明显太小"）
3. 将 required_quantity 和 completed_quantity 乘以 factor 转为基础单位
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from production.models import ProductionTask
from inventory.services.unit_conversion import UnitConversionService


class Command(BaseCommand):
    help = '修复生产任务数量：将显示单位值转换为基础单位'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='仅预览不实际修改',
        )
        parser.add_argument(
            '--force-all',
            action='store_true',
            default=False,
            help='强制转换所有 base≠display 的任务（不使用启发式判断）',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force_all = options['force_all']

        tasks = ProductionTask.objects.select_related(
            'product', 'product__base_unit', 'product__display_unit'
        ).all()

        fixed = 0
        skipped = 0

        for task in tasks:
            product = task.product
            if not product or not product.base_unit or not product.display_unit:
                continue
            if product.base_unit_id == product.display_unit_id:
                continue  # base == display，无需处理

            try:
                factor = UnitConversionService.get_factor(product, product.display_unit)
            except ValueError:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠ {task.task_no}: 无法获取换算系数，跳过'
                ))
                continue

            if factor <= 1:
                continue

            old_req = task.required_quantity
            old_comp = task.completed_quantity

            # 启发式判断：如果 required_quantity 比较小（< factor 的数量级）
            # 大概率是显示单位值
            # 例：factor=1000(吨→千克)，required=3 → 3<1000 → 可能是 3 吨
            # 但 required=3000 → 3000>=1000 → 可能已经是千克
            should_convert = force_all or (old_req < factor)

            if not should_convert:
                self.stdout.write(self.style.WARNING(
                    f'  跳过 {task.task_no}: req={old_req} >= factor={factor}，'
                    f'可能已是基础单位({product.base_unit.name})'
                ))
                skipped += 1
                continue

            new_req = old_req * factor
            new_comp = old_comp * factor

            self.stdout.write(
                f'  {task.task_no}: {product.name} '
                f'req: {old_req}{product.display_unit.name} → {new_req}{product.base_unit.name}, '
                f'comp: {old_comp} → {new_comp}'
            )

            if not dry_run:
                task.required_quantity = new_req
                task.completed_quantity = new_comp
                task.save(update_fields=['required_quantity', 'completed_quantity'])
            fixed += 1

        action = '预览' if dry_run else '修复'
        self.stdout.write(self.style.SUCCESS(
            f'\n{action}完成：共{action} {fixed} 条任务，跳过 {skipped} 条'
        ))
        if dry_run:
            self.stdout.write(self.style.NOTICE(
                '  （这是预览模式，未实际修改数据。去掉 --dry-run 执行实际修改）'
            ))
