from django.core.management.base import BaseCommand
from django.db import transaction
from inventory.models import (
    Customer, MaterialCategory, Material, Product, BOM, Inventory
)
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

    def create_materials(self):
        """创建原料分类和原料"""
        self.stdout.write('创建原料数据...')
        
        # 创建原料分类
        categories = ['基础原料', '添加剂', '填料', '助剂']
        for cat_name in categories:
            MaterialCategory.objects.get_or_create(name=cat_name)
        
        # 创建原料
        materials_data = [
            # 基础原料
            {
                'sku': 'MAT-001',
                'name': '普通硅酸盐水泥',
                'category': '基础原料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.35,
                'safety_stock': 50000,
            },
            {
                'sku': 'MAT-002',
                'name': '中砂',
                'category': '基础原料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.08,
                'safety_stock': 100000,
            },
            {
                'sku': 'MAT-003',
                'name': '细砂',
                'category': '基础原料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.10,
                'safety_stock': 80000,
            },
            {
                'sku': 'MAT-004',
                'name': '粗砂',
                'category': '基础原料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.09,
                'safety_stock': 60000,
            },
            {
                'sku': 'MAT-005',
                'name': '石灰石粉',
                'category': '基础原料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.12,
                'safety_stock': 40000,
            },
            # 添加剂
            {
                'sku': 'MAT-101',
                'name': '减水剂',
                'category': '添加剂',
                'material_type': 'auxiliary',
                'unit': 'kg',
                'unit_price': 8.50,
                'safety_stock': 2000,
            },
            {
                'sku': 'MAT-102',
                'name': '增稠剂',
                'category': '添加剂',
                'material_type': 'auxiliary',
                'unit': 'kg',
                'unit_price': 12.00,
                'safety_stock': 1500,
            },
            {
                'sku': 'MAT-103',
                'name': '早强剂',
                'category': '添加剂',
                'material_type': 'auxiliary',
                'unit': 'kg',
                'unit_price': 15.00,
                'safety_stock': 1000,
            },
            {
                'sku': 'MAT-104',
                'name': '缓凝剂',
                'category': '添加剂',
                'material_type': 'auxiliary',
                'unit': 'kg',
                'unit_price': 18.00,
                'safety_stock': 1000,
            },
            # 填料
            {
                'sku': 'MAT-201',
                'name': '粉煤灰',
                'category': '填料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.15,
                'safety_stock': 30000,
            },
            {
                'sku': 'MAT-202',
                'name': '矿渣粉',
                'category': '填料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.20,
                'safety_stock': 25000,
            },
            {
                'sku': 'MAT-203',
                'name': '硅灰',
                'category': '填料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.45,
                'safety_stock': 15000,
            },
            # 防火材料专用原料
            {
                'sku': 'MAT-301',
                'name': '膨胀珍珠岩',
                'category': '基础原料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.25,
                'safety_stock': 20000,
            },
            {
                'sku': 'MAT-302',
                'name': '阻燃剂',
                'category': '助剂',
                'material_type': 'auxiliary',
                'unit': 'kg',
                'unit_price': 25.00,
                'safety_stock': 2000,
            },
            {
                'sku': 'MAT-303',
                'name': '玻化微珠',
                'category': '基础原料',
                'material_type': 'raw',
                'unit': 'kg',
                'unit_price': 0.30,
                'safety_stock': 18000,
            },
        ]
        
        for data in materials_data:
            category = MaterialCategory.objects.get(name=data.pop('category'))
            Material.objects.get_or_create(
                sku=data['sku'],
                defaults={
                    **data,
                    'category': category,
                }
            )
        
        self.stdout.write(f'  创建了 {len(materials_data)} 种原料')

    def create_products(self):
        """创建产品"""
        self.stdout.write('创建产品数据...')
        
        products_data = [
            {
                'sku': 'PROD-001',
                'name': '普通砌筑砂浆 M5',
                'specification': '强度等级M5，适用于一般砌筑工程',
                'sale_price': 280.00,
                'safety_stock': 500,
                'unit': '袋',
            },
            {
                'sku': 'PROD-002',
                'name': '普通砌筑砂浆 M7.5',
                'specification': '强度等级M7.5，适用于一般砌筑工程',
                'sale_price': 320.00,
                'safety_stock': 500,
                'unit': '袋',
            },
            {
                'sku': 'PROD-003',
                'name': '普通砌筑砂浆 M10',
                'specification': '强度等级M10，适用于承重砌筑工程',
                'sale_price': 360.00,
                'safety_stock': 400,
                'unit': '袋',
            },
            {
                'sku': 'PROD-004',
                'name': '抹灰砂浆',
                'specification': '适用于内外墙抹灰，粘结力强',
                'sale_price': 300.00,
                'safety_stock': 600,
                'unit': '袋',
            },
            {
                'sku': 'PROD-005',
                'name': '地面找平砂浆',
                'specification': '适用于地面找平，自流平性能好',
                'sale_price': 350.00,
                'safety_stock': 400,
                'unit': '袋',
            },
            {
                'sku': 'PROD-006',
                'name': '普通硅酸盐水泥 P.O 42.5',
                'specification': '强度等级42.5，通用水泥',
                'sale_price': 450.00,
                'safety_stock': 800,
                'unit': '袋',
            },
            {
                'sku': 'PROD-007',
                'name': '普通硅酸盐水泥 P.O 32.5',
                'specification': '强度等级32.5，通用水泥',
                'sale_price': 380.00,
                'safety_stock': 1000,
                'unit': '袋',
            },
            {
                'sku': 'PROD-008',
                'name': '防火保温砂浆',
                'specification': 'A级防火，保温性能优良',
                'sale_price': 680.00,
                'safety_stock': 300,
                'unit': '袋',
            },
            {
                'sku': 'PROD-009',
                'name': '防火涂料',
                'specification': '钢结构防火涂料，耐火极限2小时',
                'sale_price': 850.00,
                'safety_stock': 200,
                'unit': '桶',
            },
            {
                'sku': 'PROD-010',
                'name': '防火密封胶',
                'specification': '防火封堵材料，阻燃性能好',
                'sale_price': 1200.00,
                'safety_stock': 150,
                'unit': '支',
            },
        ]
        
        for data in products_data:
            Product.objects.get_or_create(
                sku=data['sku'],
                defaults=data
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
        
        boms_data = [
            # 普通砌筑砂浆 M5 (每袋50kg)
            {
                'product_sku': 'PROD-001',
                'items': [
                    {'material': cement, 'quantity': 10, 'unit': 'kg'},
                    {'material': medium_sand, 'quantity': 35, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 4, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.5, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 0.5, 'unit': 'kg'},
                ],
            },
            # 普通砌筑砂浆 M7.5
            {
                'product_sku': 'PROD-002',
                'items': [
                    {'material': cement, 'quantity': 12, 'unit': 'kg'},
                    {'material': medium_sand, 'quantity': 33, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 4, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.5, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 0.5, 'unit': 'kg'},
                ],
            },
            # 普通砌筑砂浆 M10
            {
                'product_sku': 'PROD-003',
                'items': [
                    {'material': cement, 'quantity': 15, 'unit': 'kg'},
                    {'material': medium_sand, 'quantity': 30, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 4, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.5, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 0.5, 'unit': 'kg'},
                ],
            },
            # 抹灰砂浆
            {
                'product_sku': 'PROD-004',
                'items': [
                    {'material': cement, 'quantity': 12, 'unit': 'kg'},
                    {'material': fine_sand, 'quantity': 33, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 4, 'unit': 'kg'},
                    {'material': thickener, 'quantity': 0.3, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.4, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 0.3, 'unit': 'kg'},
                ],
            },
            # 地面找平砂浆
            {
                'product_sku': 'PROD-005',
                'items': [
                    {'material': cement, 'quantity': 18, 'unit': 'kg'},
                    {'material': fine_sand, 'quantity': 28, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.6, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 3, 'unit': 'kg'},
                    {'material': lime_powder, 'quantity': 0.4, 'unit': 'kg'},
                ],
            },
            # 防火保温砂浆
            {
                'product_sku': 'PROD-008',
                'items': [
                    {'material': cement, 'quantity': 15, 'unit': 'kg'},
                    {'material': expanded_pearlite, 'quantity': 20, 'unit': 'kg'},
                    {'material': vitrified_microsphere, 'quantity': 10, 'unit': 'kg'},
                    {'material': flame_retardant, 'quantity': 2, 'unit': 'kg'},
                    {'material': thickener, 'quantity': 0.5, 'unit': 'kg'},
                    {'material': water_reducer, 'quantity': 0.3, 'unit': 'kg'},
                    {'material': fly_ash, 'quantity': 2.2, 'unit': 'kg'},
                ],
            },
        ]
        
        bom_count = 0
        for bom_data in boms_data:
            product = Product.objects.get(sku=bom_data['product_sku'])
            # 删除该产品的旧BOM
            BOM.objects.filter(product=product).delete()
            
            for item_data in bom_data['items']:
                BOM.objects.create(
                    product=product,
                    material=item_data['material'],
                    quantity=item_data['quantity'],
                    unit=item_data['unit'],
                )
                bom_count += 1
        
        self.stdout.write(f'  创建了 {bom_count} 条BOM配方记录')

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
            Inventory.objects.update_or_create(
                inventory_type='product',
                product=product,
                defaults={
                    'quantity': data['quantity'],
                    'unit': product.unit,
                }
            )
        
        # 原料库存（设置为安全库存的1.5倍）
        materials = Material.objects.all()
        for material in materials:
            initial_qty = float(material.safety_stock) * 1.5
            Inventory.objects.update_or_create(
                inventory_type='material',
                material=material,
                defaults={
                    'quantity': initial_qty,
                    'unit': material.unit,
                }
            )
        
        self.stdout.write(f'  创建了成品和原料的初始库存')

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

