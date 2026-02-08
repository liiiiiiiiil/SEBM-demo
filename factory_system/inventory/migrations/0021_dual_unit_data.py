# 双单位系统迁移 - 阶段2：数据迁移
# 将旧数据填充到新字段中

from django.db import migrations


# 通用单位名称到代码的映射
UNIT_NAME_TO_CODE = {
    'kg': 'kg', '千克': 'kg', 'KG': 'kg',
    'g': 'g', '克': 'g',
    't': 't', '吨': 't',
    'lb': 'lb', '磅': 'lb',
    'm': 'm', '米': 'm',
    'cm': 'cm', '厘米': 'cm',
    'mm': 'mm', '毫米': 'mm',
    'L': 'L', '升': 'L', 'l': 'L',
    'mL': 'mL', '毫升': 'mL', 'ml': 'mL',
    '个': 'pcs', '件': 'pcs', 'pcs': 'pcs', 'PCS': 'pcs',
    '片': 'pcs_sheet', '张': 'pcs_sheet',
    '条': 'pcs_strip', '根': 'pcs_strip',
    '箱': 'box', '盒': 'box',
    '包': 'bag', '袋': 'bag',
    '桶': 'barrel', '罐': 'can',
    '瓶': 'bottle',
    '卷': 'roll',
    '套': 'set', '组': 'set',
    '板': 'board', '块': 'block',
    'm²': 'sqm', '平方米': 'sqm', '㎡': 'sqm',
}

UNIT_CODE_TO_CATEGORY = {
    'kg': 'weight', 'g': 'weight', 't': 'weight', 'lb': 'weight',
    'm': 'length', 'cm': 'length', 'mm': 'length',
    'L': 'volume', 'mL': 'volume',
    'pcs': 'quantity', 'pcs_sheet': 'quantity', 'pcs_strip': 'quantity',
    'box': 'quantity', 'bag': 'quantity', 'barrel': 'quantity',
    'can': 'quantity', 'bottle': 'quantity', 'roll': 'quantity',
    'set': 'quantity', 'board': 'quantity', 'block': 'quantity',
    'sqm': 'area',
}


def find_or_create_unit(Unit, unit_str):
    """根据单位字符串查找或创建 Unit 记录"""
    if not unit_str:
        unit_str = 'pcs'
    
    unit_str = unit_str.strip()
    
    # 先尝试按 code 查找
    unit = Unit.objects.filter(code=unit_str).first()
    if unit:
        return unit
    
    # 再按 name 查找
    unit = Unit.objects.filter(name=unit_str).first()
    if unit:
        return unit
    
    # 尝试映射
    code = UNIT_NAME_TO_CODE.get(unit_str, unit_str)
    unit = Unit.objects.filter(code=code).first()
    if unit:
        return unit
    
    # 创建新的 Unit
    category = UNIT_CODE_TO_CATEGORY.get(code, 'quantity')
    unit = Unit.objects.create(
        code=code,
        name=unit_str,
        category=category,
        symbol=unit_str,
        display_order=0,
        is_active=True,
    )
    return unit


def populate_material_units(apps, schema_editor):
    """填充 Material 的 base_unit 和 display_unit"""
    Material = apps.get_model('inventory', 'Material')
    Unit = apps.get_model('inventory', 'Unit')
    
    for material in Material.objects.all():
        changed = False
        
        # 如果 base_unit 为空，从 unit 字段创建/查找
        if not material.base_unit_id:
            unit_str = getattr(material, 'unit', '') or 'kg'
            unit_obj = find_or_create_unit(Unit, unit_str)
            material.base_unit = unit_obj
            changed = True
        
        # 设置 display_unit = base_unit（默认相同）
        if not material.display_unit_id:
            material.display_unit = material.base_unit
            changed = True
        
        if changed:
            material.save(update_fields=['base_unit', 'display_unit'])


def populate_product_units(apps, schema_editor):
    """填充 Product 的 base_unit 和 display_unit"""
    Product = apps.get_model('inventory', 'Product')
    Unit = apps.get_model('inventory', 'Unit')
    
    for product in Product.objects.all():
        changed = False
        
        if not product.base_unit_id:
            unit_str = getattr(product, 'unit', '') or '件'
            unit_obj = find_or_create_unit(Unit, unit_str)
            product.base_unit = unit_obj
            changed = True
        
        if not product.display_unit_id:
            product.display_unit = product.base_unit
            changed = True
        
        if changed:
            product.save(update_fields=['base_unit', 'display_unit'])


def populate_bom_units(apps, schema_editor):
    """填充 BOM 的 unit 字段（默认使用原料的 base_unit）"""
    BOM = apps.get_model('inventory', 'BOM')
    
    for bom in BOM.objects.select_related('material').all():
        if not bom.unit_id and bom.material and bom.material.base_unit_id:
            bom.unit = bom.material.base_unit
            bom.save(update_fields=['unit'])


def populate_stock_transaction_units(apps, schema_editor):
    """将 StockTransaction 的 unit_legacy（字符串）转换为 unit FK"""
    StockTransaction = apps.get_model('inventory', 'StockTransaction')
    Unit = apps.get_model('inventory', 'Unit')
    
    for trans in StockTransaction.objects.all():
        changed = False
        
        # 转换 unit_legacy 到 unit FK
        if not trans.unit_id:
            unit_str = getattr(trans, 'unit_legacy', '') or ''
            if unit_str:
                unit_obj = find_or_create_unit(Unit, unit_str)
                trans.unit = unit_obj
                changed = True
        
        # 填充 base_quantity
        if trans.base_quantity is None:
            trans.base_quantity = trans.quantity
            changed = True
        
        if changed:
            trans.save(update_fields=['unit', 'base_quantity'])


def migrate_packaging_units(apps, schema_editor):
    """将 MaterialPackagingUnit 和 ProductPackagingUnit 迁移到 ItemUnitConversion"""
    MaterialPackagingUnit = apps.get_model('inventory', 'MaterialPackagingUnit')
    ProductPackagingUnit = apps.get_model('inventory', 'ProductPackagingUnit')
    ItemUnitConversion = apps.get_model('inventory', 'ItemUnitConversion')
    Unit = apps.get_model('inventory', 'Unit')
    
    # 迁移物料包装单位
    for pkg in MaterialPackagingUnit.objects.all():
        # 查找或创建 target_unit
        target_unit = find_or_create_unit(Unit, pkg.packaging_unit_name)
        
        # 检查是否已存在
        exists = ItemUnitConversion.objects.filter(
            content_type='material',
            material=pkg.material,
            target_unit=target_unit,
        ).exists()
        
        if not exists:
            ItemUnitConversion.objects.create(
                content_type='material',
                material=pkg.material,
                product=None,
                base_unit=pkg.base_unit,
                target_unit=target_unit,
                factor=pkg.conversion_factor,
                is_default=pkg.is_default,
                is_active=pkg.is_active,
                remark=pkg.remark or f'从 MaterialPackagingUnit 迁移',
            )
    
    # 迁移成品包装单位
    for pkg in ProductPackagingUnit.objects.all():
        target_unit = find_or_create_unit(Unit, pkg.packaging_unit_name)
        
        exists = ItemUnitConversion.objects.filter(
            content_type='product',
            product=pkg.product,
            target_unit=target_unit,
        ).exists()
        
        if not exists:
            ItemUnitConversion.objects.create(
                content_type='product',
                material=None,
                product=pkg.product,
                base_unit=pkg.base_unit,
                target_unit=target_unit,
                factor=pkg.conversion_factor,
                is_default=pkg.is_default,
                is_active=pkg.is_active,
                remark=pkg.remark or f'从 ProductPackagingUnit 迁移',
            )


def reverse_noop(apps, schema_editor):
    """反向迁移不做任何操作（数据迁移不可逆）"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0020_dual_unit_phase1'),
    ]

    operations = [
        migrations.RunPython(populate_material_units, reverse_noop),
        migrations.RunPython(populate_product_units, reverse_noop),
        migrations.RunPython(populate_bom_units, reverse_noop),
        migrations.RunPython(populate_stock_transaction_units, reverse_noop),
        migrations.RunPython(migrate_packaging_units, reverse_noop),
    ]
