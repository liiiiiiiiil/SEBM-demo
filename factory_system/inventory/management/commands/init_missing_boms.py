from django.core.management.base import BaseCommand
from django.db import transaction
from inventory.models import Product, BOM, Material


class Command(BaseCommand):
    help = '为所有没有BOM配方的产品初始化BOM配方'

    def handle(self, *args, **options):
        self.stdout.write('开始为所有产品初始化BOM配方...')
        
        with transaction.atomic():
            # 获取所有产品
            all_products = Product.objects.all().order_by('sku')
            
            # 获取所有原料
            materials = {}
            for material in Material.objects.all():
                materials[material.sku] = material
            
            # 统计信息
            created_count = 0
            skipped_count = 0
            updated_count = 0
            
            for product in all_products:
                # 检查是否已有BOM配方
                existing_boms = BOM.objects.filter(product=product)
                
                if existing_boms.exists():
                    self.stdout.write(f'  跳过 {product.sku} - {product.name}（已有BOM配方）')
                    skipped_count += 1
                    continue
                
                # 根据产品类型创建BOM配方
                bom_items = self.get_bom_items_for_product(product, materials)
                
                if bom_items:
                    # 删除可能存在的旧BOM（虽然应该没有）
                    BOM.objects.filter(product=product).delete()
                    
                    # 创建新的BOM配方
                    for item in bom_items:
                        BOM.objects.create(
                            product=product,
                            material=item['material'],
                            quantity=item['quantity'],
                            unit=item['unit'],
                        )
                        created_count += 1
                    
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  ✓ 为 {product.sku} - {product.name} 创建了 {len(bom_items)} 条BOM配方'
                        )
                    )
                    updated_count += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ⚠ {product.sku} - {product.name} 无法创建BOM配方（缺少必要原料）'
                        )
                    )
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'BOM配方初始化完成！'
            f'  - 新创建: {updated_count} 个产品，{created_count} 条BOM记录'
            f'  - 已跳过: {skipped_count} 个产品（已有BOM配方）'
        ))

    def get_bom_items_for_product(self, product, materials):
        """根据产品返回BOM配方项"""
        sku = product.sku
        name = product.name
        
        # 获取常用原料
        cement = materials.get('MAT-001')  # 普通硅酸盐水泥
        medium_sand = materials.get('MAT-002')  # 中砂
        fine_sand = materials.get('MAT-003')  # 细砂
        lime_powder = materials.get('MAT-005')  # 石灰石粉
        water_reducer = materials.get('MAT-101')  # 减水剂
        thickener = materials.get('MAT-102')  # 增稠剂
        fly_ash = materials.get('MAT-201')  # 粉煤灰
        expanded_pearlite = materials.get('MAT-301')  # 膨胀珍珠岩
        flame_retardant = materials.get('MAT-302')  # 阻燃剂
        vitrified_microsphere = materials.get('MAT-303')  # 玻化微珠
        
        bom_items = []
        
        if sku == 'PROD-006':  # 普通硅酸盐水泥 P.O 42.5
            # 高标号水泥，需要更多添加剂
            if cement and water_reducer and fly_ash:
                bom_items = [
                    {'material': cement, 'quantity': 48, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.8, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 1.2, 'unit': 'kg'},
                ]
        
        elif sku == 'PROD-007':  # 普通硅酸盐水泥 P.O 32.5
            # 低标号水泥，添加剂较少
            if cement and water_reducer and fly_ash:
                bom_items = [
                    {'material': cement, 'quantity': 48, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.5, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 1.5, 'unit': 'kg'},
                ]
        
        elif sku == 'PROD-009':  # 防火涂料
            # 防火涂料需要阻燃剂、增稠剂等
            if cement and flame_retardant and thickener and expanded_pearlite:
                bom_items = [
                    {'material': cement, 'quantity': 15, 'unit': 'kg'},
                    {'material': flame_retardant, 'quantity': 8, 'unit': 'kg'},
                    {'material': thickener, 'quantity': 1.5, 'unit': 'kg'},
                    {'material': expanded_pearlite, 'quantity': 12, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.5, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 3, 'unit': 'kg'},
                ]
        
        elif sku == 'PROD-010':  # 防火密封胶
            # 防火密封胶需要阻燃剂、增稠剂等
            if cement and flame_retardant and thickener:
                bom_items = [
                    {'material': cement, 'quantity': 20, 'unit': 'kg'},
                    {'material': flame_retardant, 'quantity': 10, 'unit': 'kg'},
                    {'material': thickener, 'quantity': 2, 'unit': 'kg'},
                    {'material': fine_sand, 'quantity': 15, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.6, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 2.4, 'unit': 'kg'},
                ]
        
        return bom_items
