from django.core.management.base import BaseCommand
from django.db import transaction
from accounts.models import Permission


class Command(BaseCommand):
    help = '初始化系统权限数据'

    def handle(self, *args, **options):
        self.stdout.write('开始初始化权限数据...')
        
        permissions_data = [
            # 销售权限
            {
                'code': 'sales.order.create',
                'name': '创建订单',
                'category': 'sales',
                'description': '创建销售订单的权限',
            },
            {
                'code': 'sales.order.view',
                'name': '查看订单',
                'category': 'sales',
                'description': '查看自己创建的订单',
            },
            {
                'code': 'sales.order.view_all',
                'name': '查看所有订单',
                'category': 'sales',
                'description': '查看所有订单（包括其他销售员的订单）',
            },
            {
                'code': 'sales.order.edit',
                'name': '编辑订单',
                'category': 'sales',
                'description': '编辑订单信息',
            },
            {
                'code': 'sales.order.approve',
                'name': '审批订单',
                'category': 'sales',
                'description': '审批销售订单',
            },
            {
                'code': 'sales.order.delete',
                'name': '删除订单',
                'category': 'sales',
                'description': '删除订单',
            },
            # 库存权限
            {
                'code': 'inventory.view',
                'name': '查看库存',
                'category': 'inventory',
                'description': '查看库存信息',
            },
            {
                'code': 'inventory.view_product',
                'name': '查看成品库存',
                'category': 'inventory',
                'description': '查看成品库存信息',
            },
            {
                'code': 'inventory.view_material',
                'name': '查看原料库存',
                'category': 'inventory',
                'description': '查看原料库存信息',
            },
            {
                'code': 'inventory.transaction.view',
                'name': '查看库存变动',
                'category': 'inventory',
                'description': '查看库存变动记录',
            },
            {
                'code': 'inventory.customer.view',
                'name': '查看客户',
                'category': 'inventory',
                'description': '查看客户信息',
            },
            {
                'code': 'inventory.customer.create',
                'name': '创建客户',
                'category': 'inventory',
                'description': '创建新客户',
            },
            {
                'code': 'inventory.customer.edit',
                'name': '编辑客户',
                'category': 'inventory',
                'description': '编辑客户信息',
            },
            {
                'code': 'inventory.customer.delete',
                'name': '删除客户',
                'category': 'inventory',
                'description': '删除客户',
            },
            {
                'code': 'inventory.customer.manage',
                'name': '管理所有客户',
                'category': 'inventory',
                'description': '管理所有客户（包括其他销售员的客户）',
            },
            {
                'code': 'inventory.product.view',
                'name': '查看产品',
                'category': 'inventory',
                'description': '查看产品信息',
            },
            {
                'code': 'inventory.product.manage',
                'name': '管理产品',
                'category': 'inventory',
                'description': '创建、编辑、删除产品信息',
            },
            {
                'code': 'inventory.material.manage',
                'name': '管理原料',
                'category': 'inventory',
                'description': '创建、编辑、删除原料信息',
            },
            {
                'code': 'inventory.category.manage',
                'name': '管理产品/原料类别',
                'category': 'inventory',
                'description': '创建、编辑、删除产品类别和原料类别',
            },
            {
                'code': 'inventory.adjustment.create',
                'name': '创建库存调整申请',
                'category': 'inventory',
                'description': '创建库存调整申请',
            },
            {
                'code': 'inventory.adjustment.approve',
                'name': '审批库存调整申请',
                'category': 'inventory',
                'description': '审批库存调整申请',
            },
            {
                'code': 'inventory.bom.view',
                'name': '查看BOM配方',
                'category': 'inventory',
                'description': '查看BOM配方信息',
            },
            {
                'code': 'inventory.bom.manage',
                'name': '管理BOM配方',
                'category': 'inventory',
                'description': '创建、编辑、删除BOM配方',
            },
            # 生产权限
            {
                'code': 'production.task.view',
                'name': '查看生产任务',
                'category': 'production',
                'description': '查看生产任务列表和详情',
            },
            {
                'code': 'production.task.receive',
                'name': '接收生产任务',
                'category': 'production',
                'description': '接收并开始生产任务',
            },
            {
                'code': 'production.requisition.create',
                'name': '创建领料单',
                'category': 'production',
                'description': '创建原料领料单',
            },
            {
                'code': 'production.requisition.approve',
                'name': '审核领料单',
                'category': 'production',
                'description': '审核并批准领料单',
            },
            {
                'code': 'production.qc.create',
                'name': '创建质检记录',
                'category': 'production',
                'description': '创建产品质量检验记录',
            },
            {
                'code': 'production.inbound.create',
                'name': '创建入库单',
                'category': 'production',
                'description': '创建成品入库单',
            },
            # 物流权限
            {
                'code': 'logistics.shipment.view',
                'name': '查看发货单',
                'category': 'logistics',
                'description': '查看发货单信息',
            },
            {
                'code': 'logistics.shipment.create',
                'name': '创建发货单',
                'category': 'logistics',
                'description': '创建发货单',
            },
            {
                'code': 'logistics.shipment.ship',
                'name': '确认发货',
                'category': 'logistics',
                'description': '确认发货并更新订单状态',
            },
            {
                'code': 'logistics.driver.manage',
                'name': '管理司机',
                'category': 'logistics',
                'description': '创建、编辑、删除司机信息',
            },
            {
                'code': 'logistics.vehicle.manage',
                'name': '管理车辆',
                'category': 'logistics',
                'description': '创建、编辑、删除车辆信息',
            },
            # 系统权限
            {
                'code': 'system.dashboard.view',
                'name': '查看仪表板',
                'category': 'system',
                'description': '查看系统仪表板',
            },
            {
                'code': 'system.user.manage',
                'name': '管理用户',
                'category': 'system',
                'description': '创建、编辑、删除用户和权限',
            },
        ]
        
        with transaction.atomic():
            created_count = 0
            for data in permissions_data:
                permission, created = Permission.objects.get_or_create(
                    code=data['code'],
                    defaults=data
                )
                if created:
                    created_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'权限初始化完成！创建了 {created_count} 个新权限，共 {len(permissions_data)} 个权限。'))

