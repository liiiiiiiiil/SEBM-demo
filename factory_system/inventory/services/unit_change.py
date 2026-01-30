from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from inventory.models import Material, Inventory, Batch, MaterialUnitChangeHistory
try:
    from production.models import ProductionTask, MaterialRequisition, MaterialRequisitionItem
except ImportError:
    ProductionTask = None
    MaterialRequisition = None
    MaterialRequisitionItem = None
try:
    from purchase.models import PurchaseTask, PurchaseTaskItem
except ImportError:
    PurchaseTask = None
    PurchaseTaskItem = None
try:
    from sales.models import SalesOrder, SalesOrderItem
except ImportError:
    SalesOrder = None
    SalesOrderItem = None


class MaterialUnitChangeService:
    """物料单位变更服务"""
    
    @staticmethod
    def check_can_change_unit(material):
        """
        检查是否可以变更单位
        
        返回:
            {
                'can_change': bool,
                'warnings': list,  # 警告信息
                'errors': list,    # 错误信息
                'active_production_tasks': int,
                'active_purchase_tasks': int,
                'active_sales_orders': int,
            }
        """
        result = {
            'can_change': True,
            'warnings': [],
            'errors': [],
            'active_production_tasks': 0,
            'active_purchase_tasks': 0,
            'active_sales_orders': 0,
        }
        
        # 检查进行中的生产任务
        if ProductionTask and MaterialRequisitionItem:
            try:
                # 通过MaterialRequisitionItem查找使用该物料的领料单
                requisition_items = MaterialRequisitionItem.objects.filter(
                    material=material,
                    requisition__status__in=['pending', 'approved', 'issued']
                )
                # 获取关联的生产任务
                production_task_ids = requisition_items.values_list('requisition__task_id', flat=True).distinct()
                active_production_tasks = ProductionTask.objects.filter(
                    id__in=production_task_ids,
                    status__in=['pending', 'approved', 'in_progress']
                )
                result['active_production_tasks'] = active_production_tasks.count()
                
                if result['active_production_tasks'] > 0:
                    result['warnings'].append(
                        f'存在 {result["active_production_tasks"]} 个进行中的生产任务使用了该物料'
                    )
            except Exception:
                pass
        
        # 检查未完成的采购任务
        if PurchaseTask:
            try:
                active_purchase_tasks = PurchaseTask.objects.filter(
                    status__in=['pending', 'approved', 'purchasing'],
                    items__material=material
                ).distinct()
                result['active_purchase_tasks'] = active_purchase_tasks.count()
                
                if result['active_purchase_tasks'] > 0:
                    result['warnings'].append(
                        f'存在 {result["active_purchase_tasks"]} 个未完成的采购任务使用了该物料'
                    )
            except Exception:
                pass
        
        # 检查未完成的销售订单
        if SalesOrder:
            try:
                active_sales_orders = SalesOrder.objects.filter(
                    status__in=['pending', 'confirmed', 'in_production', 'completed']
                )
                # 通过BOM关联检查
                from inventory.models import BOM
                materials_in_bom = BOM.objects.filter(material=material).values_list('product_id', flat=True)
                if materials_in_bom:
                    active_sales_orders = active_sales_orders.filter(
                        items__product_id__in=materials_in_bom
                    )
                active_sales_orders = active_sales_orders.distinct()
                result['active_sales_orders'] = active_sales_orders.count()
                
                if result['active_sales_orders'] > 0:
                    result['warnings'].append(
                        f'存在 {result["active_sales_orders"]} 个未完成的销售订单使用了该物料'
                    )
            except Exception:
                pass
        
        # 如果有严重问题，设置can_change为False
        # 这里可以根据业务需求调整，比如只警告不阻止
        if result['errors']:
            result['can_change'] = False
        
        return result
    
    @staticmethod
    @transaction.atomic
    def change_unit(material, new_unit, conversion_factor, reason, changed_by, 
                   auto_approve=False, approved_by=None):
        """
        执行单位变更
        
        参数:
            material: 物料对象
            new_unit: 新单位
            conversion_factor: 转换系数（新单位数量 = 旧单位数量 × 系数）
            reason: 变更原因
            changed_by: 变更人
            auto_approve: 是否自动审批
            approved_by: 审批人
        """
        old_unit = material.unit
        old_unit_price = material.unit_price
        old_safety_stock = material.safety_stock
        
        # 获取当前库存
        try:
            inventory = Inventory.objects.get(
                inventory_type='material',
                material=material
            )
            old_inventory_quantity = inventory.quantity
        except Inventory.DoesNotExist:
            old_inventory_quantity = Decimal('0')
            inventory = None
        
        # 1. 转换物料基础数据
        # 新单价 = 旧单价 ÷ 转换系数
        new_unit_price = old_unit_price / Decimal(str(conversion_factor))
        # 新安全库存 = 旧安全库存 × 转换系数
        new_safety_stock = old_safety_stock * Decimal(str(conversion_factor))
        
        # 更新物料信息
        material.unit = new_unit
        material.unit_price = new_unit_price
        material.safety_stock = new_safety_stock
        material.save()
        
        # 2. 转换库存数量
        if inventory:
            # 新库存数量 = 旧库存数量 × 转换系数
            new_inventory_quantity = old_inventory_quantity * Decimal(str(conversion_factor))
            inventory.quantity = new_inventory_quantity
            inventory.unit = new_unit
            inventory.save()
        else:
            new_inventory_quantity = Decimal('0')
        
        # 3. 转换批次信息
        if inventory:
            batches = Batch.objects.filter(inventory=inventory)
            for batch in batches:
                # 转换批次数量
                batch.quantity = batch.quantity * Decimal(str(conversion_factor))
                # 转换批次单价
                if batch.unit_price:
                    batch.unit_price = batch.unit_price / Decimal(str(conversion_factor))
                batch.save()
        
        # 4. 记录变更历史
        change_history = MaterialUnitChangeHistory.objects.create(
            material=material,
            old_unit=old_unit,
            old_unit_price=old_unit_price,
            old_safety_stock=old_safety_stock,
            new_unit=new_unit,
            new_unit_price=new_unit_price,
            new_safety_stock=new_safety_stock,
            conversion_factor=conversion_factor,
            old_inventory_quantity=old_inventory_quantity,
            new_inventory_quantity=new_inventory_quantity,
            changed_by=changed_by,
            reason=reason,
            approval_status='auto' if auto_approve else 'approved',
            approved_by=approved_by if not auto_approve else changed_by,
            approved_at=timezone.now() if auto_approve else None
        )
        
        return change_history
