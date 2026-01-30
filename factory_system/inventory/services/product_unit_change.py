from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from inventory.models import Product, Inventory, Batch, ProductUnitChangeHistory


class ProductUnitChangeService:
    """成品单位变更服务（与MaterialUnitChangeService对称）"""
    
    @staticmethod
    def check_can_change_unit(product):
        """
        检查是否可以变更单位
        
        返回:
            {
                'can_change': bool,
                'warnings': list,  # 警告信息
                'errors': list,    # 错误信息
                'active_sales_orders': int,
                'active_production_tasks': int,
            }
        """
        result = {
            'can_change': True,
            'warnings': [],
            'errors': [],
            'active_sales_orders': 0,
            'active_production_tasks': 0,
        }
        
        # 检查未完成的销售订单
        try:
            from sales.models import SalesOrder, SalesOrderItem
            active_sales_orders = SalesOrder.objects.filter(
                status__in=['pending', 'confirmed', 'in_production', 'completed'],
                items__product=product
            ).distinct()
            result['active_sales_orders'] = active_sales_orders.count()
            
            if result['active_sales_orders'] > 0:
                result['warnings'].append(
                    f'存在 {result["active_sales_orders"]} 个未完成的销售订单使用了该成品'
                )
        except Exception:
            pass
        
        # 检查进行中的生产任务
        try:
            from production.models import ProductionTask
            active_production_tasks = ProductionTask.objects.filter(
                product=product,
                status__in=['pending', 'approved', 'in_progress']
            )
            result['active_production_tasks'] = active_production_tasks.count()
            
            if result['active_production_tasks'] > 0:
                result['warnings'].append(
                    f'存在 {result["active_production_tasks"]} 个进行中的生产任务使用了该成品'
                )
        except Exception:
            pass
        
        # 检查BOM使用情况
        try:
            from inventory.models import BOM
            bom_count = BOM.objects.filter(product=product).count()
            if bom_count > 0:
                result['warnings'].append(
                    f'该成品被 {bom_count} 个BOM配方使用，需要检查配方单位'
                )
        except Exception:
            pass
        
        # 如果有严重问题，设置can_change为False
        if result['errors']:
            result['can_change'] = False
        
        return result
    
    @staticmethod
    @transaction.atomic
    def change_unit(product, new_unit, conversion_factor, reason, changed_by, 
                   auto_approve=False, approved_by=None):
        """
        执行单位变更
        
        参数:
            product: 成品对象
            new_unit: 新单位
            conversion_factor: 转换系数（新单位数量 = 旧单位数量 × 系数）
            reason: 变更原因
            changed_by: 变更人
            auto_approve: 是否自动审批
            approved_by: 审批人
        """
        old_unit = product.unit
        old_unit_price = product.unit_price
        old_sale_price = product.sale_price
        old_safety_stock = product.safety_stock
        
        # 获取当前库存
        try:
            inventory = Inventory.objects.get(
                inventory_type='product',
                product=product
            )
            old_inventory_quantity = inventory.quantity
        except Inventory.DoesNotExist:
            old_inventory_quantity = Decimal('0')
            inventory = None
        
        # 1. 转换成品基础数据
        # 新单价 = 旧单价 ÷ 转换系数
        new_unit_price = old_unit_price / Decimal(str(conversion_factor))
        # 新售价 = 旧售价 ÷ 转换系数
        new_sale_price = old_sale_price / Decimal(str(conversion_factor)) if old_sale_price else None
        # 新安全库存 = 旧安全库存 × 转换系数
        new_safety_stock = old_safety_stock * Decimal(str(conversion_factor))
        
        # 更新成品信息
        product.unit = new_unit
        product.unit_price = new_unit_price
        if new_sale_price:
            product.sale_price = new_sale_price
        product.safety_stock = new_safety_stock
        product.save()
        
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
        change_history = ProductUnitChangeHistory.objects.create(
            product=product,
            old_unit=old_unit,
            old_unit_price=old_unit_price,
            old_sale_price=old_sale_price,
            old_safety_stock=old_safety_stock,
            new_unit=new_unit,
            new_unit_price=new_unit_price,
            new_sale_price=new_sale_price,
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
