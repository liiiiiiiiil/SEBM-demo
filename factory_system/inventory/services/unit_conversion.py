"""统一单位换算服务

替代旧版 UnitConversionService，基于 ItemUnitConversion 换算表实现。
所有换算通过 base_unit 作为中间桥梁：
    to_base:   任意单位 → 基础单位
    from_base: 基础单位 → 任意单位
    convert:   任意单位 A → 基础单位 → 任意单位 B
"""
from decimal import Decimal
from django.core.exceptions import ValidationError


class UnitConversionService:
    """统一单位换算服务"""

    @staticmethod
    def get_factor(item, unit) -> Decimal:
        """
        获取 unit 相对于 item.base_unit 的换算系数。
        返回值含义：1 unit = factor × base_unit

        参数:
            item: Material 或 Product 实例
            unit: Unit 实例或 unit code 字符串

        返回:
            Decimal — 换算系数

        异常:
            ValueError — 单位不合法时抛出
        """
        from inventory.models import Unit, ItemUnitConversion

        # 解析 unit 参数
        if isinstance(unit, str):
            try:
                unit_obj = Unit.objects.get(code=unit)
            except Unit.DoesNotExist:
                raise ValueError(f"未找到单位代码：{unit}")
        else:
            unit_obj = unit

        # 如果 unit == base_unit，factor = 1
        if unit_obj.pk == item.base_unit_id:
            return Decimal('1')

        # 仅物料主数据（product.Product）按 master_product 查；若无则按对应 inventory.Product 查（兼容旧数据）
        is_master_product = (
            type(item).__name__ == 'Product'
            and getattr(type(item), '__module__', '').startswith('product.')
        )
        if is_master_product:
            conversion = ItemUnitConversion.objects.filter(
                master_product=item,
                target_unit=unit_obj,
                is_active=True,
            ).first()
            if not conversion and item.category == 'finished':
                inv = getattr(item, 'inventory_product', None)
                if inv:
                    conversion = ItemUnitConversion.objects.filter(
                        content_type='product', product=inv,
                        target_unit=unit_obj, is_active=True,
                    ).first()
            if not conversion and item.category == 'raw':
                inv = getattr(item, 'inventory_material', None)
                if inv:
                    conversion = ItemUnitConversion.objects.filter(
                        content_type='material', material=inv,
                        target_unit=unit_obj, is_active=True,
                    ).first()
        else:
            content_type = 'material' if hasattr(item, 'material_type') else 'product'
            filters = {
                'content_type': content_type,
                'target_unit': unit_obj,
                'is_active': True,
            }
            if content_type == 'material':
                filters['material'] = item
            else:
                filters['product'] = item
            conversion = ItemUnitConversion.objects.filter(**filters).first()
        if conversion:
            return conversion.factor

        raise ValueError(
            f"单位「{unit_obj.name}」不在「{item.name}」的合法单位列表中。"
            f"请在换算表中添加该单位的换算关系。"
        )

    @staticmethod
    def to_base(item, quantity, from_unit) -> Decimal:
        """将任意单位数量转换为基础单位数量。
        
        base_qty = quantity × get_factor(item, from_unit)
        """
        quantity = Decimal(str(quantity))
        factor = UnitConversionService.get_factor(item, from_unit)
        return quantity * factor

    @staticmethod
    def from_base(item, base_quantity, to_unit) -> Decimal:
        """将基础单位数量转换为目标单位数量。
        
        target_qty = base_quantity ÷ get_factor(item, to_unit)
        """
        base_quantity = Decimal(str(base_quantity))
        factor = UnitConversionService.get_factor(item, to_unit)
        if factor == 0:
            raise ValueError("换算系数不能为0")
        return base_quantity / factor

    @staticmethod
    def convert(item, quantity, from_unit, to_unit) -> Decimal:
        """任意两个合法单位之间互转。
        
        先转为基础单位，再转为目标单位。
        """
        from inventory.models import Unit

        # 解析单位
        if isinstance(from_unit, str):
            from_unit = Unit.objects.get(code=from_unit)
        if isinstance(to_unit, str):
            to_unit = Unit.objects.get(code=to_unit)

        if from_unit.pk == to_unit.pk:
            return Decimal(str(quantity))

        base_qty = UnitConversionService.to_base(item, quantity, from_unit)
        return UnitConversionService.from_base(item, base_qty, to_unit)

    @staticmethod
    def to_display(item, base_quantity):
        """将基础单位数量转换为该物料/成品的当前显示单位数量。
        
        返回: (display_quantity, display_unit)
        """
        base_quantity = Decimal(str(base_quantity))
        display_unit = item.display_unit

        if display_unit.pk == item.base_unit_id:
            return base_quantity, display_unit

        display_qty = UnitConversionService.from_base(item, base_quantity, display_unit)
        return display_qty, display_unit

    @staticmethod
    def from_display(item, display_quantity) -> Decimal:
        """将显示单位数量转换为基础单位数量。"""
        return UnitConversionService.to_base(item, display_quantity, item.display_unit)

    @staticmethod
    def get_available_units(item) -> list:
        """
        获取物料/成品的所有可用单位列表。
        
        返回: [
            {'unit': Unit实例, 'factor': Decimal, 'is_base': True/False, 'display_text': str},
            ...
        ]
        包含 base_unit (factor=1) + 所有 ItemUnitConversion 中的 target_unit。
        """
        from inventory.models import ItemUnitConversion

        units = []

        # 添加基础单位
        if item.base_unit:
            units.append({
                'unit': item.base_unit,
                'code': item.base_unit.code,
                'name': item.base_unit.name,
                'factor': Decimal('1'),
                'is_base': True,
                'display_text': item.base_unit.name,
            })

        # 仅物料主数据（product.Product）按 master_product 查
        is_master_product = (
            type(item).__name__ == 'Product'
            and getattr(type(item), '__module__', '').startswith('product.')
        )
        if is_master_product:
            conversions = ItemUnitConversion.objects.filter(
                master_product=item, is_active=True
            ).select_related('target_unit')
        else:
            content_type = 'material' if hasattr(item, 'material_type') else 'product'
            filters = {'content_type': content_type, 'is_active': True}
            if content_type == 'material':
                filters['material'] = item
            else:
                filters['product'] = item
            conversions = ItemUnitConversion.objects.filter(**filters).select_related('target_unit')
        for conv in conversions:
            units.append({
                'unit': conv.target_unit,
                'code': conv.target_unit.code,
                'name': conv.target_unit.name,
                'factor': conv.factor,
                'is_base': False,
                'display_text': conv.get_display_text(),
            })

        return units

    @staticmethod
    def validate_bom_unit(bom_item) -> bool:
        """
        校验 BOM 行的 unit 是否合法：
        必须是 bom_item.material 的 base_unit 或其换算表中已定义的 target_unit。
        """
        from inventory.models import ItemUnitConversion

        material = bom_item.material
        unit = bom_item.unit

        if not material or not unit:
            return False

        # 是基础单位
        if unit.pk == material.base_unit_id:
            return True

        # 在换算表中
        return ItemUnitConversion.objects.filter(
            content_type='material',
            material=material,
            target_unit=unit,
            is_active=True,
        ).exists()
