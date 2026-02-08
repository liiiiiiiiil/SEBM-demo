"""
初始化单位数据：
1. 创建基础单位（千克、个）和换算目标单位（kg、吨、袋、桶、支）
2. 将所有原料和成品的 base_unit 设为「千克」，display_unit 默认也设为「千克」
3. 将其它库存物品的相关单位设为「个」
4. 创建换算关系：
   - 1 kg = 1 千克
   - 1 吨 = 1000 千克
   - 1 袋 = 100 千克
   - 1 桶 = 50 千克
   - 1 支 = 1 千克
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import models, transaction
from inventory.models import Unit, Material, Product, ItemUnitConversion, BOM, Inventory


class Command(BaseCommand):
    help = '初始化基础单位、为所有物料/成品设置基础单位、创建换算关系'

    def handle(self, *args, **options):
        with transaction.atomic():
            self.stdout.write('=== 初始化单位数据 ===\n')

            # ---------- 1. 创建 / 获取所有需要的 Unit 记录 ----------
            self.stdout.write('1. 创建基础单位和换算单位...')

            kg_unit, _ = Unit.objects.get_or_create(
                code='kg',
                defaults={'name': '千克', 'symbol': 'kg', 'category': 'weight', 'display_order': 1, 'is_active': True},
            )
            # 确保名称一致
            if kg_unit.name != '千克':
                kg_unit.name = '千克'
                kg_unit.symbol = 'kg'
                kg_unit.save(update_fields=['name', 'symbol'])
            self.stdout.write(f'  千克 (code=kg, id={kg_unit.id})')

            pcs_unit, _ = Unit.objects.get_or_create(
                code='pcs',
                defaults={'name': '个', 'symbol': '个', 'category': 'quantity', 'display_order': 10, 'is_active': True},
            )
            if pcs_unit.name != '个':
                pcs_unit.name = '个'
                pcs_unit.symbol = '个'
                pcs_unit.save(update_fields=['name', 'symbol'])
            self.stdout.write(f'  个   (code=pcs, id={pcs_unit.id})')

            # 换算目标单位
            ton_unit, _ = Unit.objects.get_or_create(
                code='ton',
                defaults={'name': '吨', 'symbol': 't', 'category': 'weight', 'display_order': 2, 'is_active': True},
            )
            self.stdout.write(f'  吨   (code=ton, id={ton_unit.id})')

            bag_unit, _ = Unit.objects.get_or_create(
                code='bag',
                defaults={'name': '袋', 'symbol': '袋', 'category': 'quantity', 'display_order': 11, 'is_active': True},
            )
            self.stdout.write(f'  袋   (code=bag, id={bag_unit.id})')

            barrel_unit, _ = Unit.objects.get_or_create(
                code='barrel',
                defaults={'name': '桶', 'symbol': '桶', 'category': 'quantity', 'display_order': 12, 'is_active': True},
            )
            self.stdout.write(f'  桶   (code=barrel, id={barrel_unit.id})')

            tube_unit, _ = Unit.objects.get_or_create(
                code='tube',
                defaults={'name': '支', 'symbol': '支', 'category': 'quantity', 'display_order': 13, 'is_active': True},
            )
            self.stdout.write(f'  支   (code=tube, id={tube_unit.id})')

            self.stdout.write('')

            # ---------- 2. 为所有原料设置 base_unit / display_unit ----------
            self.stdout.write('2. 设置所有原料的基础单位为「千克」...')
            mat_count = 0
            for material in Material.objects.all():
                changed = False
                if material.base_unit_id != kg_unit.id:
                    material.base_unit = kg_unit
                    changed = True
                if material.display_unit_id is None or material.display_unit_id != kg_unit.id:
                    material.display_unit = kg_unit
                    changed = True
                if changed:
                    # 跳过 save() 中的 base_unit 不可变校验（初始化阶段）
                    Material.objects.filter(pk=material.pk).update(
                        base_unit=kg_unit, display_unit=kg_unit,
                    )
                    mat_count += 1
            self.stdout.write(f'  更新了 {mat_count} 种原料\n')

            # ---------- 3. 为所有成品设置 base_unit / display_unit ----------
            self.stdout.write('3. 设置所有成品的基础单位为「千克」...')
            prod_count = 0
            for product in Product.objects.all():
                changed = False
                if product.base_unit_id != kg_unit.id:
                    product.base_unit = kg_unit
                    changed = True
                if product.display_unit_id is None or product.display_unit_id != kg_unit.id:
                    product.display_unit = kg_unit
                    changed = True
                if changed:
                    Product.objects.filter(pk=product.pk).update(
                        base_unit=kg_unit, display_unit=kg_unit,
                    )
                    prod_count += 1
            self.stdout.write(f'  更新了 {prod_count} 种成品\n')

            # ---------- 4. 更新所有 BOM 的 unit 为千克 ----------
            self.stdout.write('4. 设置所有 BOM 用量单位为「千克」...')
            bom_count = BOM.objects.exclude(unit=kg_unit).update(unit=kg_unit)
            self.stdout.write(f'  更新了 {bom_count} 条 BOM\n')

            # ---------- 5. 创建换算关系 ----------
            self.stdout.write('5. 创建全局换算关系（针对所有物料和成品）...')

            # 换算定义：(target_unit, factor)  含义：1 目标单位 = factor 千克
            conversions = [
                (ton_unit, Decimal('1000')),       # 1 吨 = 1000 千克
                (bag_unit, Decimal('100')),         # 1 袋 = 100 千克
                (barrel_unit, Decimal('50')),       # 1 桶 = 50 千克
                (tube_unit, Decimal('1')),          # 1 支 = 1 千克
            ]

            conv_count = 0

            # 为每个原料创建换算
            for material in Material.objects.all():
                for target_unit, factor in conversions:
                    _, created = ItemUnitConversion.objects.get_or_create(
                        content_type='material',
                        material=material,
                        target_unit=target_unit,
                        defaults={
                            'product': None,
                            'base_unit': kg_unit,
                            'factor': factor,
                            'is_default': False,
                            'is_active': True,
                            'remark': f'初始化：1{target_unit.name}={factor}千克',
                        },
                    )
                    if created:
                        conv_count += 1

            # 为每个成品创建换算
            for product in Product.objects.all():
                for target_unit, factor in conversions:
                    _, created = ItemUnitConversion.objects.get_or_create(
                        content_type='product',
                        product=product,
                        target_unit=target_unit,
                        defaults={
                            'material': None,
                            'base_unit': kg_unit,
                            'factor': factor,
                            'is_default': False,
                            'is_active': True,
                            'remark': f'初始化：1{target_unit.name}={factor}千克',
                        },
                    )
                    if created:
                        conv_count += 1

            self.stdout.write(f'  创建了 {conv_count} 条换算关系\n')

            # ---------- 6. 为「其它」类型的库存设置 other_unit ----------
            self.stdout.write('6. 设置「其它」类型库存的单位为「个」...')
            other_count = Inventory.objects.filter(
                inventory_type='other',
            ).filter(
                models.Q(other_unit__isnull=True) | ~models.Q(other_unit=pcs_unit)
            ).update(other_unit=pcs_unit)
            self.stdout.write(f'  更新了 {other_count} 条「其它」库存\n')

            self.stdout.write(self.style.SUCCESS('\n=== 单位初始化完成 ==='))
            self.stdout.write(f'  基础单位：千克 (原料/成品)、个 (其它)')
            self.stdout.write(f'  换算关系：1吨=1000千克, 1袋=100千克, 1桶=50千克, 1支=1千克')
