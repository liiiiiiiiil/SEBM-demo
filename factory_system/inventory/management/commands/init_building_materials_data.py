from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from inventory.models import (
    MaterialCategory, Material, Product, BOM, Inventory, Batch, Unit
)
from sales.models import Customer
from logistics.models import Driver, Vehicle


class Command(BaseCommand):
    help = '初始化建材生产厂的基础数据（客户、产品、原料、BOM、库存、司机车辆等）'

    def handle(self, *args, **options):
        self.stdout.write('开始初始化建材生产厂数据...')
        
        with transaction.atomic():
            # 1. 创建客户数据
            self.create_customers()
            
            # 2. 创建原料分类和原料
            self.create_materials()
            
            # 3. 创建产品
            self.create_products()
            
            # 4. 创建BOM配方
            self.create_boms()
            
            # 5. 创建初始库存
            self.create_inventory()
            
            # 6. 创建司机和车辆
            self.create_logistics_resources()
        
        self.stdout.write(self.style.SUCCESS('数据初始化完成！'))

    def create_customers(self):
        """创建客户数据"""
        self.stdout.write('创建客户数据...')
        
        customers_data = [
            {
                'name': '华建建筑工程有限公司',
                'contact_person': '张经理',
                'phone': '13800138001',
                'address': '北京市朝阳区建国路88号',
                'credit_level': 'A',
            },
            {
                'name': '中建装饰集团',
                'contact_person': '李总',
                'phone': '13800138002',
                'address': '上海市浦东新区世纪大道1000号',
                'credit_level': 'A',
            },
            {
                'name': '万科地产开发公司',
                'contact_person': '王主任',
                'phone': '13800138003',
                'address': '深圳市南山区科技园',
                'credit_level': 'A',
            },
            {
                'name': '绿地建设集团',
                'contact_person': '赵经理',
                'phone': '13800138004',
                'address': '广州市天河区天河路123号',
                'credit_level': 'B',
            },
            {
                'name': '恒大建筑公司',
                'contact_person': '陈工',
                'phone': '13800138005',
                'address': '杭州市西湖区文三路456号',
                'credit_level': 'B',
            },
            {
                'name': '碧桂园装饰公司',
                'contact_person': '刘经理',
                'phone': '13800138006',
                'address': '成都市锦江区春熙路789号',
                'credit_level': 'B',
            },
        ]
        
        for data in customers_data:
            Customer.objects.get_or_create(
                name=data['name'],
                defaults=data
            )
        
        self.stdout.write(f'  创建了 {len(customers_data)} 个客户')

    def _ensure_units(self):
        """确保基础单位存在"""
        unit_data = [
            ('kg', '千克', 'weight', 'kg'),
            ('g', '克', 'weight', 'g'),
            ('t', '吨', 'weight', 't'),
            ('m', '米', 'length', 'm'),
            ('cm', '厘米', 'length', 'cm'),
            ('mm', '毫米', 'length', 'mm'),
            ('L', '升', 'volume', 'L'),
            ('mL', '毫升', 'volume', 'mL'),
            ('pcs', '个/件', 'quantity', '个'),
            ('bag', '袋', 'quantity', '袋'),
            ('barrel', '桶', 'quantity', '桶'),
            ('tube', '支', 'quantity', '支'),
            ('box', '箱', 'quantity', '箱'),
            ('sqm', '平方米', 'area', '㎡'),
        ]
        units = {}
        for code, name, category, symbol in unit_data:
            unit, _ = Unit.objects.get_or_create(
                code=code,
                defaults={
                    'name': name,
                    'category': category,
                    'symbol': symbol,
                    'is_active': True,
                }
            )
            units[code] = unit
        return units

    def create_materials(self):
        """创建原料分类和原料"""
        self.stdout.write('创建原料数据...')
        
        units = self._ensure_units()
        kg_unit = units['kg']
        
        # 创建原料分类
        categories = ['基础原料', '添加剂', '填料', '助剂']
        for cat_name in categories:
            MaterialCategory.objects.get_or_create(name=cat_name)
        
        # 创建原料（所有原料以 kg 为基础单位）
        materials_data = [
            # 基础原料
            {'sku': 'MAT-001', 'name': '普通硅酸盐水泥', 'category': '基础原料', 'material_type': 'raw', 'unit_price': 0.35, 'safety_stock': 50000},
            {'sku': 'MAT-002', 'name': '中砂', 'category': '基础原料', 'material_type': 'raw', 'unit_price': 0.08, 'safety_stock': 100000},
            {'sku': 'MAT-003', 'name': '细砂', 'category': '基础原料', 'material_type': 'raw', 'unit_price': 0.10, 'safety_stock': 80000},
            {'sku': 'MAT-004', 'name': '粗砂', 'category': '基础原料', 'material_type': 'raw', 'unit_price': 0.09, 'safety_stock': 60000},
            {'sku': 'MAT-005', 'name': '石灰石粉', 'category': '基础原料', 'material_type': 'raw', 'unit_price': 0.12, 'safety_stock': 40000},
            # 添加剂
            {'sku': 'MAT-101', 'name': '减水剂', 'category': '添加剂', 'material_type': 'auxiliary', 'unit_price': 8.50, 'safety_stock': 2000},
            {'sku': 'MAT-102', 'name': '增稠剂', 'category': '添加剂', 'material_type': 'auxiliary', 'unit_price': 12.00, 'safety_stock': 1500},
            {'sku': 'MAT-103', 'name': '早强剂', 'category': '添加剂', 'material_type': 'auxiliary', 'unit_price': 15.00, 'safety_stock': 1000},
            {'sku': 'MAT-104', 'name': '缓凝剂', 'category': '添加剂', 'material_type': 'auxiliary', 'unit_price': 18.00, 'safety_stock': 1000},
            # 填料
            {'sku': 'MAT-201', 'name': '粉煤灰', 'category': '填料', 'material_type': 'raw', 'unit_price': 0.15, 'safety_stock': 30000},
            {'sku': 'MAT-202', 'name': '矿渣粉', 'category': '填料', 'material_type': 'raw', 'unit_price': 0.20, 'safety_stock': 25000},
            {'sku': 'MAT-203', 'name': '硅灰', 'category': '填料', 'material_type': 'raw', 'unit_price': 0.45, 'safety_stock': 15000},
            # 防火材料专用原料
            {'sku': 'MAT-301', 'name': '膨胀珍珠岩', 'category': '基础原料', 'material_type': 'raw', 'unit_price': 0.25, 'safety_stock': 20000},
            {'sku': 'MAT-302', 'name': '阻燃剂', 'category': '助剂', 'material_type': 'auxiliary', 'unit_price': 25.00, 'safety_stock': 2000},
            {'sku': 'MAT-303', 'name': '玻化微珠', 'category': '基础原料', 'material_type': 'raw', 'unit_price': 0.30, 'safety_stock': 18000},
        ]
        
        for data in materials_data:
            category = MaterialCategory.objects.get(name=data.pop('category'))
            Material.objects.get_or_create(
                sku=data['sku'],
                defaults={
                    **data,
                    'category': category,
                    'base_unit': kg_unit,
                    'display_unit': kg_unit,
                }
            )
        
        self.stdout.write(f'  创建了 {len(materials_data)} 种原料')

    def create_products(self):
        """创建产品"""
        self.stdout.write('创建产品数据...')
        
        units = self._ensure_units()
        bag_unit = units['bag']
        barrel_unit = units['barrel']
        tube_unit = units['tube']
        
        products_data = [
            {'sku': 'PROD-001', 'name': '普通砌筑砂浆 M5', 'specification': '强度等级M5，适用于一般砌筑工程', 'sale_price': 280.00, 'safety_stock': 500, 'unit_code': 'bag'},
            {'sku': 'PROD-002', 'name': '普通砌筑砂浆 M7.5', 'specification': '强度等级M7.5，适用于一般砌筑工程', 'sale_price': 320.00, 'safety_stock': 500, 'unit_code': 'bag'},
            {'sku': 'PROD-003', 'name': '普通砌筑砂浆 M10', 'specification': '强度等级M10，适用于承重砌筑工程', 'sale_price': 360.00, 'safety_stock': 400, 'unit_code': 'bag'},
            {'sku': 'PROD-004', 'name': '抹灰砂浆', 'specification': '适用于内外墙抹灰，粘结力强', 'sale_price': 300.00, 'safety_stock': 600, 'unit_code': 'bag'},
            {'sku': 'PROD-005', 'name': '地面找平砂浆', 'specification': '适用于地面找平，自流平性能好', 'sale_price': 350.00, 'safety_stock': 400, 'unit_code': 'bag'},
            {'sku': 'PROD-006', 'name': '普通硅酸盐水泥 P.O 42.5', 'specification': '强度等级42.5，通用水泥', 'sale_price': 450.00, 'safety_stock': 800, 'unit_code': 'bag'},
            {'sku': 'PROD-007', 'name': '普通硅酸盐水泥 P.O 32.5', 'specification': '强度等级32.5，通用水泥', 'sale_price': 380.00, 'safety_stock': 1000, 'unit_code': 'bag'},
            {'sku': 'PROD-008', 'name': '防火保温砂浆', 'specification': 'A级防火，保温性能优良', 'sale_price': 680.00, 'safety_stock': 300, 'unit_code': 'bag'},
            {'sku': 'PROD-009', 'name': '防火涂料', 'specification': '钢结构防火涂料，耐火极限2小时', 'sale_price': 850.00, 'safety_stock': 200, 'unit_code': 'barrel'},
            {'sku': 'PROD-010', 'name': '防火密封胶', 'specification': '防火封堵材料，阻燃性能好', 'sale_price': 1200.00, 'safety_stock': 150, 'unit_code': 'tube'},
        ]
        
        for data in products_data:
            unit_code = data.pop('unit_code')
            product_unit = units[unit_code]
            Product.objects.get_or_create(
                sku=data['sku'],
                defaults={
                    **data,
                    'base_unit': product_unit,
                    'display_unit': product_unit,
                }
            )
        
        self.stdout.write(f'  创建了 {len(products_data)} 种产品')

    def create_boms(self):
        """创建BOM配方"""
        self.stdout.write('创建BOM配方数据...')
        
        # 获取原料
        cement = Material.objects.get(sku='MAT-001')
        medium_sand = Material.objects.get(sku='MAT-002')
        fine_sand = Material.objects.get(sku='MAT-003')
        coarse_sand = Material.objects.get(sku='MAT-004')
        lime_powder = Material.objects.get(sku='MAT-005')
        water_reducer = Material.objects.get(sku='MAT-101')
        thickener = Material.objects.get(sku='MAT-102')
        fly_ash = Material.objects.get(sku='MAT-201')
        expanded_pearlite = Material.objects.get(sku='MAT-301')
        flame_retardant = Material.objects.get(sku='MAT-302')
        vitrified_microsphere = Material.objects.get(sku='MAT-303')
        
        # 每袋产品按 50kg 干混料计，配合比参考常见砌筑/抹灰/地面/保温砂浆工艺
        boms_data = [
            # 普通砌筑砂浆 M5（每袋50kg，水泥:砂约1:5，石灰石粉适量）
            {
                'product_sku': 'PROD-001',
                'items': [
                    {'material': cement, 'quantity': 9, 'unit': 'kg'},
                    {'material': medium_sand, 'quantity': 37.5, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 2.5, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.4, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 0.6, 'unit': 'kg'},
                ],
            },
            # 普通砌筑砂浆 M7.5（强度略高，水泥用量增加）
            {
                'product_sku': 'PROD-002',
                'items': [
                    {'material': cement, 'quantity': 11, 'unit': 'kg'},
                    {'material': medium_sand, 'quantity': 35.5, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 2.5, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.5, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 0.5, 'unit': 'kg'},
                ],
            },
            # 普通砌筑砂浆 M10（承重砌筑，水泥:砂约1:4）
            {
                'product_sku': 'PROD-003',
                'items': [
                    {'material': cement, 'quantity': 14, 'unit': 'kg'},
                    {'material': medium_sand, 'quantity': 32.5, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 2.5, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.5, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 0.5, 'unit': 'kg'},
                ],
            },
            # 抹灰砂浆（细砂为主，增稠/减水微量）
            {
                'product_sku': 'PROD-004',
                'items': [
                    {'material': cement, 'quantity': 11, 'unit': 'kg'},
                    {'material': fine_sand, 'quantity': 35.5, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 2.5, 'unit': 'kg'},
                    {'material': thickener, 'quantity': 0.25, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.4, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 0.35, 'unit': 'kg'},
                ],
            },
            # 地面找平砂浆（水泥略多、粉煤灰改善和易性）
            {
                'product_sku': 'PROD-005',
                'items': [
                    {'material': cement, 'quantity': 17, 'unit': 'kg'},
                    {'material': fine_sand, 'quantity': 29, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.6, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 2.5, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 0.9, 'unit': 'kg'},
                ],
            },
            # 防火保温砂浆（轻骨料为主，阻燃剂约2%）
            {
                'product_sku': 'PROD-008',
                'items': [
                    {'material': cement, 'quantity': 14, 'unit': 'kg'},
                    {'material': expanded_pearlite, 'quantity': 20, 'unit': 'kg'},
                    {'material': vitrified_microsphere, 'quantity': 10, 'unit': 'kg'},
                    {'material': flame_retardant, 'quantity': 1.2, 'unit': 'kg'},
                    {'material': thickener, 'quantity': 0.4, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.3, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 4.1, 'unit': 'kg'},
                ],
            },
        ]
        
        # 获取 kg 单位用于 BOM
        units = self._ensure_units()
        kg_unit = units['kg']
        
        bom_count = 0
        for bom_data in boms_data:
            product = Product.objects.get(sku=bom_data['product_sku'])
            # 删除该产品的旧BOM
            BOM.objects.filter(product=product).delete()
            
            for item_data in bom_data['items']:
                # 查找 BOM 用量单位（默认使用原料的 base_unit）
                bom_unit = kg_unit
                if 'unit' in item_data:
                    unit_str = item_data['unit']
                    bom_unit = Unit.objects.filter(name=unit_str).first() or \
                               Unit.objects.filter(code=unit_str).first() or \
                               item_data['material'].base_unit or kg_unit
                
                BOM.objects.create(
                    product=product,
                    material=item_data['material'],
                    quantity=item_data['quantity'],
                    unit=bom_unit,
                )
                bom_count += 1
        
        self.stdout.write(f'  创建了 {bom_count} 条BOM配方记录')

    def _ensure_inventory_batch(self, inventory, quantity, sku_prefix):
        """确保库存有对应的批次记录。若已有批次则跳过，否则创建初始批次。"""
        from decimal import Decimal
        batch_total = Batch.objects.filter(inventory=inventory).aggregate(
            total=__import__('django.db.models', fromlist=['Sum']).Sum('quantity')
        )['total'] or Decimal('0')
        missing = Decimal(str(quantity)) - batch_total
        if missing > 0:
            batch_no = f"{sku_prefix}-INIT-{timezone.now().strftime('%Y%m%d')}"
            Batch.objects.get_or_create(
                batch_no=batch_no,
                inventory=inventory,
                defaults={
                    'batch_date': timezone.now().date(),
                    'quantity': missing,
                    'remark': '初始化数据自动创建批次',
                },
            )

    def create_inventory(self):
        """创建初始库存"""
        self.stdout.write('创建初始库存数据...')
        
        # 成品库存
        product_inventory = [
            {'sku': 'PROD-001', 'quantity': 800},
            {'sku': 'PROD-002', 'quantity': 600},
            {'sku': 'PROD-003', 'quantity': 500},
            {'sku': 'PROD-004', 'quantity': 900},
            {'sku': 'PROD-005', 'quantity': 450},
            {'sku': 'PROD-006', 'quantity': 1200},
            {'sku': 'PROD-007', 'quantity': 1500},
            {'sku': 'PROD-008', 'quantity': 400},
            {'sku': 'PROD-009', 'quantity': 250},
            {'sku': 'PROD-010', 'quantity': 180},
        ]
        
        for data in product_inventory:
            product = Product.objects.get(sku=data['sku'])
            inv, _ = Inventory.objects.update_or_create(
                inventory_type='product',
                product=product,
                defaults={
                    'quantity': data['quantity'],
                }
            )
            self._ensure_inventory_batch(inv, data['quantity'], data['sku'])
        
        # 原料库存（设置为安全库存的1.5倍）
        materials = Material.objects.all()
        for material in materials:
            initial_qty = float(material.safety_stock) * 1.5
            inv, _ = Inventory.objects.update_or_create(
                inventory_type='material',
                material=material,
                defaults={
                    'quantity': initial_qty,
                }
            )
            self._ensure_inventory_batch(inv, initial_qty, material.sku)
        
        self.stdout.write(f'  创建了成品和原料的初始库存（含批次记录）')

    def create_logistics_resources(self):
        """创建司机和车辆"""
        self.stdout.write('创建物流资源数据...')
        
        drivers_data = [
            {
                'name': '张师傅',
                'phone': '13900139001',
                'license_no': 'A1234567890123456',
                'license_type': 'A2',
            },
            {
                'name': '李师傅',
                'phone': '13900139002',
                'license_no': 'B1234567890123456',
                'license_type': 'B2',
            },
            {
                'name': '王师傅',
                'phone': '13900139003',
                'license_no': 'C1234567890123456',
                'license_type': 'B2',
            },
            {
                'name': '赵师傅',
                'phone': '13900139004',
                'license_no': 'D1234567890123456',
                'license_type': 'A2',
            },
        ]
        
        for data in drivers_data:
            Driver.objects.get_or_create(
                license_no=data['license_no'],
                defaults=data
            )
        
        vehicles_data = [
            {
                'plate_no': '京A12345',
                'vehicle_type': 'truck',
                'model': '解放J6P 6x4',
                'capacity': 20.0,
            },
            {
                'plate_no': '京B67890',
                'vehicle_type': 'truck',
                'model': '东风天龙 6x4',
                'capacity': 18.0,
            },
            {
                'plate_no': '京C11111',
                'vehicle_type': 'truck',
                'model': '重汽豪沃 6x4',
                'capacity': 22.0,
            },
            {
                'plate_no': '京D22222',
                'vehicle_type': 'van',
                'model': '金杯海狮',
                'capacity': 2.0,
            },
            {
                'plate_no': '京E33333',
                'vehicle_type': 'pickup',
                'model': '长城风骏5',
                'capacity': 1.5,
            },
        ]
        
        for data in vehicles_data:
            Vehicle.objects.get_or_create(
                plate_no=data['plate_no'],
                defaults=data
            )
        
        self.stdout.write(f'  创建了 {len(drivers_data)} 个司机和 {len(vehicles_data)} 辆车')

