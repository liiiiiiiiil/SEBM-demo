# 产品主数据 -> 库存/业务层同步（保持 inventory.Product / Material / BOM 与 product 一致）
from django.db import transaction


def sync_master_to_inventory_product(master):
    """将 product.Product（成品）同步到 inventory.Product。若存在同 SKU 且已解除主数据关联的库存成品行则复用。"""
    from inventory.models import Product as InvProduct, ProductCategory
    if master.category != 'finished':
        return None
    inv = InvProduct.objects.filter(master_product=master).first()
    if inv:
        inv.sku = master.sku
        inv.name = master.name
        inv.base_unit_id = master.base_unit_id
        inv.display_unit_id = master.display_unit_id or master.base_unit_id
        inv.unit_price = master.unit_price
        inv.sale_price = master.sale_price or 0
        inv.safety_stock = master.safety_stock
        inv.specification = master.specification or ''
        inv.save(update_fields=['sku', 'name', 'base_unit_id', 'display_unit_id', 'unit_price', 'sale_price', 'safety_stock', 'specification'])
        return inv
    # 删除主数据后库存成品行可能仍存在（master_product_id 已置空），复用同 SKU 的孤儿行避免 UNIQUE(sku) 冲突
    inv = InvProduct.objects.filter(sku=master.sku, master_product_id__isnull=True).first()
    if inv:
        inv.master_product = master
        inv.name = master.name
        inv.base_unit_id = master.base_unit_id
        inv.display_unit_id = master.display_unit_id or master.base_unit_id
        inv.unit_price = master.unit_price
        inv.sale_price = master.sale_price or 0
        inv.safety_stock = master.safety_stock
        inv.specification = master.specification or ''
        inv.save(update_fields=['master_product_id', 'name', 'base_unit_id', 'display_unit_id', 'unit_price', 'sale_price', 'safety_stock', 'specification'])
        return inv
    category_id = ProductCategory.objects.first().id if ProductCategory.objects.exists() else None
    return InvProduct.objects.create(
        master_product=master,
        sku=master.sku,
        name=master.name,
        base_unit_id=master.base_unit_id,
        display_unit_id=master.display_unit_id or master.base_unit_id,
        unit_price=master.unit_price,
        sale_price=master.sale_price or 0,
        safety_stock=master.safety_stock,
        specification=master.specification or '',
        category_id=category_id,
    )


def sync_master_to_inventory_material(master):
    """将 product.Product（原料/半成品/辅料/工具/办公物品）同步到 inventory.Material。material_type 与主数据 category 一致。"""
    from inventory.models import Material as InvMaterial, MaterialCategory
    if master.category not in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
        return None
    material_type = master.category
    inv = InvMaterial.objects.filter(master_product=master).first()
    if inv:
        inv.sku = master.sku
        inv.name = master.name
        inv.base_unit_id = master.base_unit_id
        inv.display_unit_id = master.display_unit_id or master.base_unit_id
        inv.unit_price = master.unit_price
        inv.safety_stock = master.safety_stock
        inv.material_type = material_type
        inv.save(update_fields=['sku', 'name', 'base_unit_id', 'display_unit_id', 'unit_price', 'safety_stock', 'material_type'])
        return inv
    inv = InvMaterial.objects.filter(sku=master.sku, master_product_id__isnull=True).first()
    if inv:
        inv.master_product = master
        inv.name = master.name
        inv.base_unit_id = master.base_unit_id
        inv.display_unit_id = master.display_unit_id or master.base_unit_id
        inv.unit_price = master.unit_price
        inv.safety_stock = master.safety_stock
        inv.material_type = material_type
        inv.save(update_fields=['master_product_id', 'name', 'base_unit_id', 'display_unit_id', 'unit_price', 'safety_stock', 'material_type'])
        return inv
    category_id = MaterialCategory.objects.first().id if MaterialCategory.objects.exists() else None
    return InvMaterial.objects.create(
        master_product=master,
        sku=master.sku,
        name=master.name,
        base_unit_id=master.base_unit_id,
        display_unit_id=master.display_unit_id or master.base_unit_id,
        unit_price=master.unit_price,
        safety_stock=master.safety_stock,
        material_type=material_type,
        category_id=category_id,
    )


def sync_bom_to_inventory(product_bom):
    """将 product.BOM 同步到 inventory.BOM（生产等仍读 inventory.BOM）"""
    from inventory.models import BOM as InvBOM
    inv_product = getattr(product_bom.product, 'inventory_product', None)
    inv_material = getattr(product_bom.component, 'inventory_material', None)
    if not inv_product or not inv_material:
        return
    InvBOM.objects.update_or_create(
        product=inv_product,
        material=inv_material,
        defaults={'quantity': product_bom.quantity, 'unit_id': product_bom.unit_id},
    )


def convert_other_inventory_to_material(master):
    """产品类型从「其它」改为原料/半成品/辅料/工具/办公物品时：将原 Inventory(other) 就地转为 Inventory(material)，
    这样库存分类会正确归到新类型下，且历史批次与变动记录仍指向同一 Inventory。
    查找顺序：先按 product_master；若无则按 other_name 匹配已脱钩的「其它」行（修复历史错位数据）。"""
    from inventory.models import Inventory
    if master.category not in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
        return None
    other_inv = Inventory.objects.filter(inventory_type='other', product_master=master).first()
    if not other_inv:
        # 修复历史错位：主数据已是物料类型但「其它」行已被脱钩，用名称匹配（仅当该主数据尚无物料库存行时）
        has_material_inv = Inventory.objects.filter(
            inventory_type='material', material__master_product=master
        ).exists()
        if not has_material_inv:
            other_inv = Inventory.objects.filter(
                inventory_type='other',
                product_master_id__isnull=True,
                other_name=master.name.strip(),
            ).first()
    inv_material = sync_master_to_inventory_material(master)
    if not inv_material:
        return None
    if other_inv:
        # 就地转换：同一行改为 material 类型，避免删除导致 StockTransaction.PROTECT 失败
        other_inv.inventory_type = 'material'
        other_inv.material = inv_material
        other_inv.product_id = None
        other_inv.product_master_id = master.pk
        other_inv.other_name = ''
        other_inv.other_unit_id = None
        other_inv.other_unit_price = None
        other_inv.save(update_fields=[
            'inventory_type', 'material_id', 'product_id', 'product_master_id',
            'other_name', 'other_unit_id', 'other_unit_price',
        ])
        return other_inv
    # 无原「其它」库存行时，确保存在 material 库存行以便在分类下展示
    inv, _ = Inventory.objects.get_or_create(
        inventory_type='material',
        material=inv_material,
        defaults={'quantity': 0},
    )
    return inv


def sync_master_to_inventory_other(master):
    """将 product.Product（其它）同步到 inventory.Inventory（inventory_type='other'）"""
    from inventory.models import Inventory
    if master.category != 'other':
        return None
    inv = Inventory.objects.filter(inventory_type='other', product_master=master).first()
    if inv:
        inv.other_name = master.name
        inv.other_unit_id = master.base_unit_id
        inv.other_unit_price = master.unit_price or 0
        inv.save(update_fields=['other_name', 'other_unit_id', 'other_unit_price'])
        return inv
    other_name = master.name
    if Inventory.objects.filter(inventory_type='other', other_name=other_name).exists():
        other_name = f"{master.name}({master.sku})"
    return Inventory.objects.create(
        inventory_type='other',
        product_master=master,
        other_name=other_name,
        other_unit=master.base_unit,
        other_unit_price=master.unit_price or 0,
        quantity=0,
    )


def delete_inventory_bom_for_product_bom(product_bom):
    """删除 product.BOM 时同步删除 inventory.BOM"""
    from inventory.models import BOM as InvBOM
    inv_product = getattr(product_bom.product, 'inventory_product', None)
    inv_material = getattr(product_bom.component, 'inventory_material', None)
    if inv_product and inv_material:
        InvBOM.objects.filter(product=inv_product, material=inv_material).delete()
