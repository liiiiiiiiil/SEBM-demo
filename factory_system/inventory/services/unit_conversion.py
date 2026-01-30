from decimal import Decimal
from django.core.exceptions import ValidationError


class UnitConversionService:
    """单位转换服务类"""
    
    @staticmethod
    def convert_quantity(quantity, from_unit, to_unit, material=None, product=None):
        """
        转换数量
        
        参数:
            quantity: 数量（Decimal或数字）
            from_unit: 源单位（str）
            to_unit: 目标单位（str）
            material: 物料对象（可选）
            product: 成品对象（可选）
        
        返回:
            转换后的数量（Decimal）
        
        异常:
            ValueError: 无法转换时抛出
        """
        quantity = Decimal(str(quantity))
        
        # 如果单位相同，直接返回
        if from_unit == to_unit:
            return quantity
        
        # 优先使用物料
        item = material or product
        if not item:
            raise ValueError("需要提供物料或成品对象以进行单位转换")
        
        # 获取基础单位
        base_unit_code = item.get_base_unit() if hasattr(item, 'get_base_unit') else item.unit
        
        # 情况1：从包装单位转换为基础单位
        if from_unit != base_unit_code:
            packaging_unit = None
            if material:
                packaging_unit = material.packaging_units.filter(
                    packaging_unit_name=from_unit,
                    is_active=True
                ).first()
            elif product and hasattr(product, 'packaging_units'):
                packaging_unit = product.packaging_units.filter(
                    packaging_unit_name=from_unit,
                    is_active=True
                ).first()
            
            if packaging_unit:
                # 转换为基础单位
                base_quantity = packaging_unit.convert_to_base(quantity)
                
                # 如果目标单位是基础单位，直接返回
                if to_unit == base_unit_code:
                    return base_quantity
                
                # 如果目标单位也是包装单位
                target_packaging = None
                if material:
                    target_packaging = material.packaging_units.filter(
                        packaging_unit_name=to_unit,
                        is_active=True
                    ).first()
                elif product and hasattr(product, 'packaging_units'):
                    target_packaging = product.packaging_units.filter(
                        packaging_unit_name=to_unit,
                        is_active=True
                    ).first()
                
                if target_packaging:
                    # 从基础单位转换为目标包装单位
                    return target_packaging.convert_from_base(base_quantity)
        
        # 情况2：从基础单位转换为包装单位
        if from_unit == base_unit_code:
            packaging_unit = None
            if material:
                packaging_unit = material.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
            elif product and hasattr(product, 'packaging_units'):
                packaging_unit = product.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
            
            if packaging_unit:
                return packaging_unit.convert_from_base(quantity)
        
        # 无法转换
        raise ValueError(
            f"无法转换：{from_unit} → {to_unit}。"
            f"请检查物料/成品是否定义了相应的包装单位。"
        )
    
    @staticmethod
    def convert_price(price, from_unit, to_unit, material=None, product=None):
        """
        转换单价
        
        参数:
            price: 单价（Decimal或数字）
            from_unit: 源单位（str）
            to_unit: 目标单位（str）
            material: 物料对象（可选）
            product: 成品对象（可选）
        
        返回:
            转换后的单价（Decimal）
        
        说明:
            单价转换公式：新单价 = 旧单价 ÷ 转换系数
            例如：0.5元/kg，1袋=100kg，则50元/袋
        """
        price = Decimal(str(price))
        
        if from_unit == to_unit:
            return price
        
        # 获取转换系数
        conversion_factor = UnitConversionService.get_conversion_factor(
            from_unit, to_unit, material, product
        )
        
        # 单价转换：新单价 = 旧单价 ÷ 转换系数
        return price / conversion_factor
    
    @staticmethod
    def get_conversion_factor(from_unit, to_unit, material=None, product=None):
        """获取转换系数"""
        if from_unit == to_unit:
            return Decimal('1')
        
        item = material or product
        if not item:
            raise ValueError("需要提供物料或成品对象")
        
        base_unit_code = item.get_base_unit() if hasattr(item, 'get_base_unit') else item.unit
        
        # 从包装单位到基础单位
        if from_unit != base_unit_code:
            packaging_unit = None
            if material:
                packaging_unit = material.packaging_units.filter(
                    packaging_unit_name=from_unit,
                    is_active=True
                ).first()
            elif product and hasattr(product, 'packaging_units'):
                packaging_unit = product.packaging_units.filter(
                    packaging_unit_name=from_unit,
                    is_active=True
                ).first()
            
            if packaging_unit:
                factor = packaging_unit.conversion_factor
                
                # 目标单位是基础单位
                if to_unit == base_unit_code:
                    return factor
                
                # 目标单位也是包装单位
                target_packaging = None
                if material:
                    target_packaging = material.packaging_units.filter(
                        packaging_unit_name=to_unit,
                        is_active=True
                    ).first()
                elif product and hasattr(product, 'packaging_units'):
                    target_packaging = product.packaging_units.filter(
                        packaging_unit_name=to_unit,
                        is_active=True
                    ).first()
                
                if target_packaging:
                    # 从包装单位A到包装单位B
                    # 例如：从"袋"到"箱"，需要知道1箱=多少袋
                    # 这里假设都是基于同一个基础单位
                    if packaging_unit.base_unit == target_packaging.base_unit:
                        return factor / target_packaging.conversion_factor
        
        # 从基础单位到包装单位
        if from_unit == base_unit_code:
            packaging_unit = None
            if material:
                packaging_unit = material.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
            elif product and hasattr(product, 'packaging_units'):
                packaging_unit = product.packaging_units.filter(
                    packaging_unit_name=to_unit,
                    is_active=True
                ).first()
            
            if packaging_unit:
                return Decimal('1') / packaging_unit.conversion_factor
        
        raise ValueError(f"无法获取转换系数：{from_unit} → {to_unit}")
    
    @staticmethod
    def get_available_units(material=None, product=None):
        """
        获取可用的单位列表（基础单位 + 包装单位）
        
        返回:
            [
                {'code': 'kg', 'name': '千克', 'type': 'base'},
                {'code': '袋', 'name': '袋(100kg/袋)', 'type': 'packaging'},
            ]
        """
        units = []
        item = material or product
        
        if not item:
            return units
        
        # 添加基础单位
        base_unit_code = item.get_base_unit() if hasattr(item, 'get_base_unit') else item.unit
        base_unit_obj = None
        if hasattr(item, 'base_unit') and item.base_unit:
            base_unit_obj = item.base_unit
            units.append({
                'code': base_unit_obj.code,
                'name': base_unit_obj.name,
                'type': 'base',
                'display_text': base_unit_obj.name
            })
        else:
            units.append({
                'code': base_unit_code,
                'name': base_unit_code,
                'type': 'base',
                'display_text': base_unit_code
            })
        
        # 添加包装单位
        packaging_units = []
        if material:
            packaging_units = material.packaging_units.filter(is_active=True)
        elif product and hasattr(product, 'packaging_units'):
            packaging_units = product.packaging_units.filter(is_active=True)
        
        for pkg_unit in packaging_units:
            units.append({
                'code': pkg_unit.packaging_unit_name,
                'name': pkg_unit.packaging_unit_name,
                'type': 'packaging',
                'display_text': pkg_unit.get_display_text(),
                'conversion_factor': pkg_unit.conversion_factor,
                'base_unit': pkg_unit.base_unit.code
            })
        
        return units
