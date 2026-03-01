# 产品管理模块：以 product.Product / product.BOM 为字典源，同步到 inventory 供业务使用
from urllib.parse import urlencode
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.core.paginator import Paginator
from django.db import transaction
from decimal import Decimal

from accounts.decorators import role_or_permission_required
from product.models import Product as MasterProduct, BOM as MasterBOM
from product.forms import ProductCreateForm, ProductMasterForm, MaterialMasterForm, OtherMasterForm, ProductEditForm
from product.services.sync import (
    sync_master_to_inventory_product,
    sync_master_to_inventory_material,
    sync_master_to_inventory_other,
    convert_other_inventory_to_material,
    sync_bom_to_inventory,
    delete_inventory_bom_for_product_bom,
)
from inventory.models import (
    Product as InvProduct,
    Material as InvMaterial,
    Unit,
    ItemUnitConversion,
)


def _category_display(category):
    return dict(MasterProduct.CATEGORY_CHOICES).get(category, category)


def _unlink_master_from_inventory(master, from_category):
    """类型变更前：解除产品主数据与库存旧类型的关联"""
    if from_category == 'finished':
        inv = getattr(master, 'inventory_product', None)
        if inv:
            inv.master_product_id = None
            inv.save(update_fields=['master_product_id'])
    elif from_category in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
        InvMaterial.objects.filter(master_product=master).update(master_product_id=None)
    elif from_category == 'other':
        from inventory.models import Inventory
        Inventory.objects.filter(inventory_type='other', product_master=master).update(product_master_id=None)


# ---------- 统一产品列表（来自 product.Product） ----------

@login_required
@role_or_permission_required('warehouse', 'production', 'ceo', permission_code='inventory.product.view')
def product_list(request):
    """产品列表：从产品主数据表 product.Product 读取；按分类标签页展示（成品/原料/其他）"""
    search = request.GET.get('search', '')
    category_filter = request.GET.get('category', '') or '成品'  # 默认成品

    qs = MasterProduct.objects.select_related('base_unit', 'display_unit').all()
    if search:
        qs = qs.filter(Q(sku__icontains=search) | Q(name__icontains=search))
    cat_map = {
        '成品': 'finished', '半成品': 'semi', '原料': 'raw',
        '辅料': 'auxiliary', '工具': 'tool', '办公物品': 'office', '其它': 'other',
    }
    qs = qs.filter(category=cat_map.get(category_filter, 'finished'))

    rows = []
    for p in qs:
        bom_count = MasterBOM.objects.filter(product=p).count() if p.is_finished() else 0
        if p.category == 'finished':
            item_type = 'product'
        elif p.category == 'raw':
            item_type = 'material'
        elif p.category == 'auxiliary':
            item_type = 'auxiliary'
        else:
            item_type = 'other'
        rows.append({
            'item_type': item_type,
            'pk': p.pk,
            'sku': p.sku,
            'name': p.name,
            'category_display': _category_display(p.category),
            'unit_price': p.unit_price,
            'unit_display': p.display_unit.name if p.display_unit_id else (p.base_unit.name if p.base_unit_id else '-'),
            'display_unit_price': p.get_display_unit_price(),
            'has_bom': bom_count > 0,
            'bom_count': bom_count,
            'created_at': p.created_at,
        })
    _order = {'成品': 0, '半成品': 1, '原料': 2, '辅料': 3, '工具': 4, '办公物品': 5, '其它': 6}
    rows.sort(key=lambda x: (_order.get(x['category_display'], 9), x['sku']))

    paginator = Paginator(rows, 20)
    page_obj = paginator.get_page(request.GET.get('page'))
    extra_params = '&'.join(k + '=' + v for k, v in request.GET.items() if k != 'page' and v)

    context = {
        'product_rows': page_obj,
        'search': search,
        'category_filter': category_filter,
        'extra_params': extra_params,
        'can_manage': getattr(request.user, 'profile', None) and request.user.profile.has_permission('inventory.product.manage'),
        'can_manage_bom': getattr(request.user, 'profile', None) and request.user.profile.has_permission('inventory.bom.manage'),
    }
    return render(request, 'product/product_list.html', context)


# ---------- 统一创建（选择类别：成品/原料/其他） ----------

@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def item_create(request):
    """统一创建：选择类别（成品/原料/其他）后保存并同步到库存"""
    initial_category = request.GET.get('category', '') or None  # 支持 ?category=finished 等预选
    if initial_category and initial_category not in ('finished', 'semi', 'raw', 'auxiliary', 'tool', 'office', 'other'):
        initial_category = None
    if request.method == 'POST':
        form = ProductCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                master = form.save(commit=False)
                if not master.display_unit_id:
                    master.display_unit_id = master.base_unit_id
                if master.category == 'finished':
                    master.sale_price = master.unit_price
                master.save()
                if master.category == 'finished':
                    sync_master_to_inventory_product(master)
                elif master.category in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
                    sync_master_to_inventory_material(master)
                else:
                    sync_master_to_inventory_other(master)
            cat_label = dict(MasterProduct.CATEGORY_CHOICES).get(master.category, master.category)
            messages.success(request, f'{cat_label} {master.name} 创建成功')
            return redirect('product:product_list')
    else:
        form = ProductCreateForm(initial_category=initial_category)
    return render(request, 'product/item_form.html', {'form': form, 'title': '新建'})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def item_edit(request, pk):
    """编辑产品主数据：可修改类型（category）及基本信息；类型变更时解除旧库存关联并同步到新类型"""
    master = get_object_or_404(MasterProduct, pk=pk)
    if request.method == 'GET' and master.category in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
        # 修复错位：若主数据已是物料类型但库存仍为「其它」，打开编辑页时自动转换到对应分类
        convert_other_inventory_to_material(master)
    if request.method == 'POST':
        form = ProductEditForm(request.POST, instance=master)
        if form.is_valid():
            old_category = master.category
            with transaction.atomic():
                form.save()
                new_category = master.category
                if master.category == 'finished':
                    master.sale_price = master.unit_price
                    master.save(update_fields=['sale_price'])
                if old_category != new_category:
                    if old_category == 'other' and new_category in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
                        # 其它→物料：就地转换 Inventory(other) 为 Inventory(material)，库存分类才能正确
                        convert_other_inventory_to_material(master)
                    else:
                        _unlink_master_from_inventory(master, old_category)
                if new_category == 'finished':
                    sync_master_to_inventory_product(master)
                elif new_category in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
                    sync_master_to_inventory_material(master)
                elif new_category == 'other':
                    sync_master_to_inventory_other(master)
            cat_label = _category_display(master.category)
            messages.success(request, f'{cat_label} {master.name} 更新成功')
            return redirect(reverse('product:product_list') + '?' + urlencode({'category': cat_label}))
    else:
        form = ProductEditForm(instance=master)
    title = f'编辑物料（当前类型：{_category_display(master.category)}）'
    return render(request, 'product/material_form.html', {'form': form, 'title': title, 'material': master, 'item_type': 'edit'})


# ---------- 成品 CRUD（product.Product category=finished + 同步到 inventory.Product） ----------

@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def product_create(request):
    """创建成品（保留 URL，重定向到统一创建并预选成品）"""
    return redirect('product:item_create' + '?category=finished')


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def product_edit(request, pk):
    """编辑成品（保留 URL，重定向到统一编辑）"""
    return redirect('product:item_edit', pk=pk)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def product_delete(request, pk):
    """删除成品：解除 inventory 关联后删除 product.Product"""
    master = get_object_or_404(MasterProduct, pk=pk, category='finished')
    if request.method == 'POST':
        with transaction.atomic():
            inv = getattr(master, 'inventory_product', None)
            if inv:
                inv.master_product_id = None
                inv.save(update_fields=['master_product_id'])
            master.delete()
        messages.success(request, f'产品 {master.name} 已删除')
        return redirect('product:product_list')
    return render(request, 'product/product_confirm_delete.html', {'product': master, 'item_type': 'product'})


# ---------- 原料 CRUD（product.Product category=raw + 同步到 inventory.Material） ----------

@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def material_create(request):
    """创建原料（保留 URL，重定向到统一创建并预选原料）"""
    return redirect('product:item_create' + '?category=raw')


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def material_edit(request, pk):
    """编辑原料（保留 URL，重定向到统一编辑）"""
    return redirect('product:item_edit', pk=pk)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def material_delete(request, pk):
    """删除原料：解除 inventory 关联后删除 product.Product"""
    master = get_object_or_404(MasterProduct, pk=pk, category='raw')
    if request.method == 'POST':
        with transaction.atomic():
            inv = getattr(master, 'inventory_material', None)
            if inv:
                inv.master_product_id = None
                inv.save(update_fields=['master_product_id'])
            master.delete()
        messages.success(request, f'原料 {master.name} 已删除')
        return redirect('product:product_list')
    return render(request, 'product/material_confirm_delete.html', {'material': master, 'item_type': 'material'})


# ---------- 辅料 CRUD（product.Product category=auxiliary，与原料并列；同步到 inventory.Material） ----------

@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def auxiliary_create(request):
    """创建辅料（重定向到统一创建并预选辅料）"""
    return redirect('product:item_create' + '?category=auxiliary')


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def auxiliary_edit(request, pk):
    """编辑辅料（保留 URL，重定向到统一编辑）"""
    return redirect('product:item_edit', pk=pk)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def auxiliary_delete(request, pk):
    """删除辅料：解除 inventory 关联后删除 product.Product"""
    master = get_object_or_404(MasterProduct, pk=pk, category='auxiliary')
    if request.method == 'POST':
        with transaction.atomic():
            InvMaterial.objects.filter(master_product=master).update(master_product_id=None)
            master.delete()
        messages.success(request, f'辅料 {master.name} 已删除')
        return redirect('product:product_list' + '?category=辅料')
    return render(request, 'product/material_confirm_delete.html', {'material': master, 'item_type': 'auxiliary'})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def auxiliary_packaging_unit_list(request, pk):
    """辅料单位换算：与原料一致，走 inventory.Material 换算，重定向到物料单位换算页"""
    master = get_object_or_404(MasterProduct, pk=pk, category='auxiliary')
    return redirect('product:material_packaging_unit_list', pk=pk)


# ---------- 其它 CRUD（product.Product category=other + 同步到 inventory type=other） ----------

@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def other_create(request):
    """创建其它物品（保留 URL，重定向到统一创建并预选其他）"""
    return redirect('product:item_create' + '?category=other')


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def other_edit(request, pk):
    """编辑半成品/辅料/办公物品/其它（保留 URL，重定向到统一编辑）"""
    return redirect('product:item_edit', pk=pk)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.product.manage')
def other_delete(request, pk):
    """删除半成品/辅料/办公物品/其它：解除 inventory 关联后删除 product.Product"""
    master = get_object_or_404(MasterProduct, pk=pk, category__in=['semi', 'auxiliary', 'tool', 'office', 'other'])
    if request.method == 'POST':
        cat_label = _category_display(master.category)
        name = master.name
        with transaction.atomic():
            for inv in master.inventory_records.filter(inventory_type='other'):
                inv.product_master_id = None
                inv.save(update_fields=['product_master_id'])
            InvMaterial.objects.filter(master_product=master).update(master_product_id=None)
            master.delete()
        messages.success(request, f'{cat_label} {name} 已删除')
        return redirect('product:product_list')
    return render(request, 'product/material_confirm_delete.html', {'material': master, 'item_type': 'other'})


# ---------- BOM 配方（product.BOM，仅成品；同步到 inventory.BOM） ----------

@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.view')
def bom_list(request):
    """BOM 配方列表（来自 product.BOM）"""
    boms = MasterBOM.objects.select_related('product', 'component', 'unit').all()
    product_filter = request.GET.get('product', '')
    if product_filter:
        boms = boms.filter(product_id=product_filter)
    products = MasterProduct.objects.filter(category='finished').order_by('sku')
    bom_by_product = {}
    for bom in boms:
        pid = bom.product.id
        if pid not in bom_by_product:
            bom_by_product[pid] = {'product': bom.product, 'items': []}
        bom_by_product[pid]['items'].append(bom)
    context = {
        'bom_by_product': bom_by_product,
        'products': products,
        'product_filter': product_filter,
        'can_manage': getattr(request.user, 'profile', None) and request.user.profile.has_permission('inventory.bom.manage'),
    }
    return render(request, 'product/bom_list.html', context)


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.manage')
def bom_edit(request, product_id):
    """编辑某成品的 BOM（product.BOM）；component 为 product.Product 原料"""
    product = get_object_or_404(MasterProduct, pk=product_id, category='finished')
    bom_items = MasterBOM.objects.filter(product=product).select_related(
        'component', 'component__base_unit', 'component__display_unit', 'unit'
    ).prefetch_related('component__inventory_material', 'component__inventory_material__unit_conversions').order_by('component__sku')
    available = MasterProduct.objects.filter(
        category__in=['raw', 'semi', 'auxiliary', 'tool', 'office', 'other']
    ).select_related('base_unit', 'display_unit').prefetch_related(
        'inventory_material', 'inventory_material__unit_conversions'
    ).order_by('sku')
    existing_ids = bom_items.values_list('component_id', flat=True)
    available_materials = available.exclude(id__in=existing_ids)
    context = {
        'product': product,
        'bom_items': bom_items,
        'available_materials': available_materials,
    }
    return render(request, 'product/bom_edit.html', context)


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.manage')
def bom_item_add(request, product_id):
    """添加 BOM 行（product.BOM + 同步到 inventory.BOM）；仅使用原料基础单位，不可选单位。"""
    product = get_object_or_404(MasterProduct, pk=product_id, category='finished')
    if request.method == 'POST':
        component_id = request.POST.get('material')
        quantity = request.POST.get('quantity')
        if not component_id or quantity is None or quantity == '':
            messages.error(request, '请填写完整的原料和用量')
            return redirect('product:bom_edit', product_id=product_id)
        try:
            component = MasterProduct.objects.get(
                pk=component_id,
                category__in=['raw', 'semi', 'auxiliary', 'tool', 'office', 'other'],
            )
            unit = component.base_unit
            qty = Decimal(quantity)
            if qty <= 0:
                messages.error(request, '用量必须大于0')
                return redirect('product:bom_edit', product_id=product_id)
            if MasterBOM.objects.filter(product=product, component=component).exists():
                messages.error(request, f'原料「{component.name}」已在该产品的 BOM 中')
                return redirect('product:bom_edit', product_id=product_id)
            with transaction.atomic():
                bom = MasterBOM.objects.create(product=product, component=component, quantity=qty, unit=unit)
                sync_bom_to_inventory(bom)
            messages.success(request, f'已添加原料「{component.name}」到 BOM 配方')
        except (MasterProduct.DoesNotExist, ValueError, Exception) as e:
            messages.error(request, f'添加失败：{str(e)}')
    return redirect('product:bom_edit', product_id=product_id)


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.manage')
def bom_item_edit(request, product_id, bom_id):
    """编辑 BOM 行：仅可修改用量，单位固定为原料基础单位，不可修改。"""
    product = get_object_or_404(MasterProduct, pk=product_id, category='finished')
    bom_item = get_object_or_404(MasterBOM, pk=bom_id, product=product)
    if request.method == 'POST':
        quantity = request.POST.get('quantity')
        if not quantity and quantity != 0:
            messages.error(request, '请填写用量')
            return redirect('product:bom_edit', product_id=product_id)
        try:
            qty = Decimal(quantity)
            if qty <= 0:
                messages.error(request, '用量必须大于0')
                return redirect('product:bom_edit', product_id=product_id)
            with transaction.atomic():
                bom_item.quantity = qty
                bom_item.unit = bom_item.component.base_unit
                bom_item.save()
                sync_bom_to_inventory(bom_item)
            messages.success(request, f'已更新原料「{bom_item.component.name}」的配方')
        except (ValueError, Exception) as e:
            messages.error(request, f'更新失败：{str(e)}')
    return redirect('product:bom_edit', product_id=product_id)


@login_required
@role_or_permission_required('production', 'ceo', permission_code='inventory.bom.manage')
def bom_item_delete(request, product_id, bom_id):
    """删除 BOM 行"""
    product = get_object_or_404(MasterProduct, pk=product_id, category='finished')
    bom_item = get_object_or_404(MasterBOM, pk=bom_id, product=product)
    if request.method == 'POST':
        with transaction.atomic():
            delete_inventory_bom_for_product_bom(bom_item)
            name = bom_item.component.name
            bom_item.delete()
        messages.success(request, f'已从 BOM 配方中删除原料「{name}」')
    return redirect('product:bom_edit', product_id=product_id)


# ---------- 成品单位换算（仍用 inventory.ItemUnitConversion + inventory.Product，由 master 解析） ----------

def _get_inv_product_for_master(master_id):
    """根据 product.Product id 取得 inventory.Product（用于单位换算表）"""
    master = get_object_or_404(MasterProduct, pk=master_id)
    if not master.is_finished():
        return None, master
    inv = getattr(master, 'inventory_product', None)
    if not inv:
        sync_master_to_inventory_product(master)
        inv = getattr(master, 'inventory_product', None)
    return inv, master


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_packaging_unit_list(request, product_id):
    """成品单位换算表（product_id 为 product.Product id，换算表在 inventory.Product 上）"""
    inv, master = _get_inv_product_for_master(product_id)
    if not inv:
        messages.error(request, '仅成品可配置单位换算')
        return redirect('product:product_list')
    conversions = ItemUnitConversion.objects.filter(
        content_type='product', product=inv
    ).select_related('base_unit', 'target_unit').order_by('created_at')
    context = {'product': master, 'conversions': conversions, 'inv_product': inv}
    return render(request, 'product/product_packaging_unit_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_packaging_unit_create(request, product_id):
    inv, master = _get_inv_product_for_master(product_id)
    if not inv:
        messages.error(request, '仅成品可配置单位换算')
        return redirect('product:product_list')
    if request.method == 'POST':
        target_unit_id = request.POST.get('target_unit', '').strip()
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        if not target_unit_id or not factor:
            messages.error(request, '请填写目标单位和换算系数')
            return redirect('product:product_packaging_unit_create', product_id=product_id)
        try:
            target_unit = Unit.objects.get(pk=target_unit_id)
            factor_val = Decimal(factor)
            if target_unit.pk == inv.base_unit_id:
                messages.error(request, '目标单位不能与基础单位相同')
                return redirect('product:product_packaging_unit_create', product_id=product_id)
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('product:product_packaging_unit_create', product_id=product_id)
            if ItemUnitConversion.objects.filter(content_type='product', product=inv, target_unit=target_unit).exists():
                messages.error(request, f'已存在到「{target_unit.name}」的换算关系')
                return redirect('product:product_packaging_unit_create', product_id=product_id)
            ItemUnitConversion.objects.create(
                content_type='product', product=inv, master_product=master, base_unit=inv.base_unit,
                target_unit=target_unit, factor=factor_val, is_default=is_default, remark=remark,
                is_active=True,
            )
            messages.success(request, f'换算关系创建成功')
            return redirect('product:product_packaging_unit_list', product_id=product_id)
        except (Unit.DoesNotExist, ValueError, Exception) as e:
            messages.error(request, f'创建失败：{str(e)}')
    existing_unit_ids = list(ItemUnitConversion.objects.filter(content_type='product', product=inv).values_list('target_unit_id', flat=True))
    existing_unit_ids.append(inv.base_unit_id)
    available_units = Unit.objects.filter(is_active=True).exclude(pk__in=existing_unit_ids)
    return render(request, 'product/product_packaging_unit_form.html', {'product': master, 'available_units': available_units})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_packaging_unit_edit(request, product_id, packaging_unit_id):
    inv, master = _get_inv_product_for_master(product_id)
    if not inv:
        messages.error(request, '仅成品可配置单位换算')
        return redirect('product:product_list')
    conversion = get_object_or_404(
        ItemUnitConversion.objects.select_related('target_unit'),
        pk=packaging_unit_id, content_type='product', product=inv,
    )
    if request.method == 'POST':
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        remark = request.POST.get('remark', '').strip()
        if not factor:
            messages.error(request, '请填写换算系数')
            return redirect('product:product_packaging_unit_edit', product_id=product_id, packaging_unit_id=packaging_unit_id)
        try:
            factor_val = Decimal(factor)
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('product:product_packaging_unit_edit', product_id=product_id, packaging_unit_id=packaging_unit_id)
            conversion.factor = factor_val
            conversion.is_default = is_default
            conversion.is_active = is_active
            conversion.remark = remark
            conversion.save()
            messages.success(request, '换算关系更新成功')
            return redirect('product:product_packaging_unit_list', product_id=product_id)
        except (ValueError, Exception) as e:
            messages.error(request, f'更新失败：{str(e)}')
    return render(request, 'product/product_packaging_unit_form.html', {'product': master, 'conversion': conversion})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_packaging_unit_delete(request, product_id, packaging_unit_id):
    inv, master = _get_inv_product_for_master(product_id)
    if not inv:
        return redirect('product:product_list')
    conversion = get_object_or_404(ItemUnitConversion, pk=packaging_unit_id, content_type='product', product=inv)
    if request.method == 'POST':
        if inv.display_unit_id == conversion.target_unit_id:
            messages.error(request, '无法删除：该单位是当前显示单位，请先修改显示单位')
            return redirect('product:product_packaging_unit_list', product_id=product_id)
        conversion.delete()
        messages.success(request, '换算关系已删除')
        return redirect('product:product_packaging_unit_list', product_id=product_id)
    return redirect('product:product_packaging_unit_list', product_id=product_id)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_set_display_unit(request, product_id, unit_id):
    inv, master = _get_inv_product_for_master(product_id)
    if not inv:
        return redirect('product:product_list')
    unit = get_object_or_404(Unit, pk=unit_id)
    if request.method == 'POST':
        master.display_unit = unit
        master.save(update_fields=['display_unit'])
        sync_master_to_inventory_product(master)
        messages.success(request, f'显示单位已切换为「{unit.name}」')
        return redirect('product:product_packaging_unit_list', product_id=product_id)
    return redirect('product:product_packaging_unit_list', product_id=product_id)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_unit_change_request(request, product_id):
    inv, master = _get_inv_product_for_master(product_id)
    if not inv:
        return redirect('product:product_list')
    if request.method == 'POST':
        new_display_unit_id = request.POST.get('display_unit', '').strip()
        if not new_display_unit_id:
            messages.error(request, '请选择新的显示单位')
            return redirect('product:product_unit_change_request', product_id=product_id)
        try:
            new_display_unit = Unit.objects.get(pk=new_display_unit_id)
            if new_display_unit.pk != master.base_unit_id:
                if not ItemUnitConversion.objects.filter(
                    content_type='product', product=inv, target_unit=new_display_unit, is_active=True
                ).exists():
                    messages.error(request, '该单位不在换算表中，请先添加')
                    return redirect('product:product_unit_change_request', product_id=product_id)
            old = master.display_unit
            master.display_unit = new_display_unit
            master.save(update_fields=['display_unit'])
            sync_master_to_inventory_product(master)
            messages.success(request, f'显示单位已从「{old.name}」修改为「{new_display_unit.name}」')
            return redirect('product:product_packaging_unit_list', product_id=product_id)
        except Unit.DoesNotExist:
            messages.error(request, '选择的单位不存在')
        except Exception as e:
            messages.error(request, f'修改失败：{str(e)}')
    available_units = [inv.base_unit]
    for conv in ItemUnitConversion.objects.filter(content_type='product', product=inv, is_active=True).select_related('target_unit'):
        available_units.append(conv.target_unit)
    return render(request, 'product/product_unit_change_form.html', {'product': master, 'available_units': available_units})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def product_unit_change_history(request, product_id):
    messages.info(request, '显示单位变更不影响数据，无需记录历史')
    return redirect('product:product_packaging_unit_list', product_id=product_id)


# ---------- 原料单位换算（product_id 为 product.Product id，换算表在 inventory.Material 上） ----------

def _get_inv_material_for_master(master_id):
    """根据 product.Product id 取得 inventory.Material（用于单位换算表；原料/半成品/辅料/办公物品有 Material）"""
    master = get_object_or_404(MasterProduct, pk=master_id)
    if master.category not in ('raw', 'semi', 'auxiliary', 'tool', 'office'):
        return None, master
    inv = getattr(master, 'inventory_material', None)
    if not inv:
        sync_master_to_inventory_material(master)
        inv = getattr(master, 'inventory_material', None)
    return inv, master


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def material_packaging_unit_list(request, pk):
    """原料单位换算表（pk 为 product.Product id）"""
    inv, master = _get_inv_material_for_master(pk)
    if not inv:
        messages.error(request, '仅原料/半成品/辅料/工具/办公物品可配置单位换算')
        return redirect('product:product_list')
    conversions = ItemUnitConversion.objects.filter(
        content_type='material', material=inv
    ).select_related('base_unit', 'target_unit').order_by('created_at')
    context = {'master': master, 'material': inv, 'conversions': conversions}
    return render(request, 'product/material_packaging_unit_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def material_packaging_unit_create(request, pk):
    inv, master = _get_inv_material_for_master(pk)
    if not inv:
        messages.error(request, '仅原料/半成品/辅料/工具/办公物品可配置单位换算')
        return redirect('product:product_list')
    if request.method == 'POST':
        target_unit_id = request.POST.get('target_unit', '').strip()
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        if not target_unit_id or not factor:
            messages.error(request, '请填写目标单位和换算系数')
            return redirect('product:material_packaging_unit_create', pk=pk)
        try:
            target_unit = Unit.objects.get(pk=target_unit_id)
            factor_val = Decimal(factor)
            if target_unit.pk == inv.base_unit_id:
                messages.error(request, '目标单位不能与基础单位相同')
                return redirect('product:material_packaging_unit_create', pk=pk)
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('product:material_packaging_unit_create', pk=pk)
            if ItemUnitConversion.objects.filter(content_type='material', material=inv, target_unit=target_unit).exists():
                messages.error(request, f'已存在到「{target_unit.name}」的换算关系')
                return redirect('product:material_packaging_unit_create', pk=pk)
            ItemUnitConversion.objects.create(
                content_type='material', material=inv, master_product=master,
                base_unit=inv.base_unit, target_unit=target_unit, factor=factor_val,
                is_default=is_default, remark=remark, is_active=True,
            )
            messages.success(request, '换算关系创建成功')
            return redirect('product:material_packaging_unit_list', pk=pk)
        except (Unit.DoesNotExist, ValueError, Exception) as e:
            messages.error(request, f'创建失败：{str(e)}')
    existing_unit_ids = list(ItemUnitConversion.objects.filter(content_type='material', material=inv).values_list('target_unit_id', flat=True))
    existing_unit_ids.append(inv.base_unit_id)
    available_units = Unit.objects.filter(is_active=True).exclude(pk__in=existing_unit_ids)
    return render(request, 'product/material_packaging_unit_form.html', {'master': master, 'material': inv, 'available_units': available_units})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def material_packaging_unit_edit(request, pk, packaging_unit_id):
    inv, master = _get_inv_material_for_master(pk)
    if not inv:
        return redirect('product:product_list')
    conversion = get_object_or_404(
        ItemUnitConversion.objects.select_related('target_unit'),
        pk=packaging_unit_id, content_type='material', material=inv,
    )
    if request.method == 'POST':
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        remark = request.POST.get('remark', '').strip()
        if not factor:
            messages.error(request, '请填写换算系数')
            return redirect('product:material_packaging_unit_edit', pk=pk, packaging_unit_id=packaging_unit_id)
        try:
            factor_val = Decimal(factor)
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('product:material_packaging_unit_edit', pk=pk, packaging_unit_id=packaging_unit_id)
            conversion.factor = factor_val
            conversion.is_default = is_default
            conversion.is_active = is_active
            conversion.remark = remark
            conversion.save()
            messages.success(request, '换算关系更新成功')
            return redirect('product:material_packaging_unit_list', pk=pk)
        except (ValueError, Exception) as e:
            messages.error(request, f'更新失败：{str(e)}')
    return render(request, 'product/material_packaging_unit_form.html', {'master': master, 'material': inv, 'conversion': conversion})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def material_packaging_unit_delete(request, pk, packaging_unit_id):
    inv, master = _get_inv_material_for_master(pk)
    if not inv:
        return redirect('product:product_list')
    conversion = get_object_or_404(ItemUnitConversion, pk=packaging_unit_id, content_type='material', material=inv)
    if request.method == 'POST':
        from inventory.models import BOM
        if BOM.objects.filter(material=inv, unit=conversion.target_unit).exists():
            messages.error(request, f'无法删除：该换算单位「{conversion.target_unit.name}」正在被 BOM 配方使用')
            return redirect('product:material_packaging_unit_list', pk=pk)
        if inv.display_unit_id == conversion.target_unit_id:
            messages.error(request, '无法删除：该单位是当前显示单位，请先修改显示单位')
            return redirect('product:material_packaging_unit_list', pk=pk)
        conversion.delete()
        messages.success(request, '换算关系已删除')
        return redirect('product:material_packaging_unit_list', pk=pk)
    return redirect('product:material_packaging_unit_list', pk=pk)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def material_set_display_unit(request, pk, unit_id):
    inv, master = _get_inv_material_for_master(pk)
    if not inv:
        return redirect('product:product_list')
    unit = get_object_or_404(Unit, pk=unit_id)
    if request.method == 'POST':
        if unit.pk == inv.base_unit_id:
            inv.display_unit = unit
            inv.save(update_fields=['display_unit'])
            master.display_unit = unit
            master.save(update_fields=['display_unit'])
            sync_master_to_inventory_material(master)
            messages.success(request, f'显示单位已切换为「{unit.name}」（基础单位）')
        else:
            if not ItemUnitConversion.objects.filter(content_type='material', material=inv, target_unit=unit, is_active=True).exists():
                messages.error(request, f'「{unit.name}」不在该物料的换算表中')
                return redirect('product:material_packaging_unit_list', pk=pk)
            inv.display_unit = unit
            inv.save(update_fields=['display_unit'])
            master.display_unit = unit
            master.save(update_fields=['display_unit'])
            sync_master_to_inventory_material(master)
            messages.success(request, f'显示单位已切换为「{unit.name}」')
        return redirect('product:material_packaging_unit_list', pk=pk)
    return redirect('product:material_packaging_unit_list', pk=pk)


# ---------- 其他类型单位换算（content_type=other，master_product） ----------

@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def other_packaging_unit_list(request, pk):
    """半成品/辅料/办公物品/其它 单位换算：有 Material 的走物料换算，其它走 content_type=other"""
    master = get_object_or_404(MasterProduct, pk=pk)
    if master.category in ('semi', 'auxiliary', 'tool', 'office'):
        return redirect('product:material_packaging_unit_list', pk=pk)
    if master.category != 'other':
        messages.error(request, '仅半成品/辅料/工具/办公物品/其它可在此配置单位换算')
        return redirect('product:product_list')
    conversions = ItemUnitConversion.objects.filter(
        content_type='other', master_product=master
    ).select_related('base_unit', 'target_unit').order_by('created_at')
    context = {'master': master, 'conversions': conversions}
    return render(request, 'product/other_packaging_unit_list.html', context)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def other_packaging_unit_create(request, pk):
    master = get_object_or_404(MasterProduct, pk=pk)
    if master.category in ('semi', 'auxiliary', 'tool', 'office'):
        return redirect('product:material_packaging_unit_create', pk=pk)
    if master.category != 'other':
        messages.error(request, '仅其它类型可在此配置单位换算')
        return redirect('product:product_list')
    if request.method == 'POST':
        target_unit_id = request.POST.get('target_unit', '').strip()
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        remark = request.POST.get('remark', '').strip()
        if not target_unit_id or not factor:
            messages.error(request, '请填写目标单位和换算系数')
            return redirect('product:other_packaging_unit_create', pk=pk)
        try:
            target_unit = Unit.objects.get(pk=target_unit_id)
            factor_val = Decimal(factor)
            if target_unit.pk == master.base_unit_id:
                messages.error(request, '目标单位不能与基础单位相同')
                return redirect('product:other_packaging_unit_create', pk=pk)
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('product:other_packaging_unit_create', pk=pk)
            if ItemUnitConversion.objects.filter(content_type='other', master_product=master, target_unit=target_unit).exists():
                messages.error(request, f'已存在到「{target_unit.name}」的换算关系')
                return redirect('product:other_packaging_unit_create', pk=pk)
            ItemUnitConversion.objects.create(
                content_type='other', master_product=master,
                base_unit=master.base_unit, target_unit=target_unit, factor=factor_val,
                is_default=is_default, remark=remark, is_active=True,
            )
            messages.success(request, '换算关系创建成功')
            return redirect('product:other_packaging_unit_list', pk=pk)
        except (Unit.DoesNotExist, ValueError, Exception) as e:
            messages.error(request, f'创建失败：{str(e)}')
    existing_unit_ids = list(ItemUnitConversion.objects.filter(content_type='other', master_product=master).values_list('target_unit_id', flat=True))
    existing_unit_ids.append(master.base_unit_id)
    available_units = Unit.objects.filter(is_active=True).exclude(pk__in=existing_unit_ids)
    return render(request, 'product/other_packaging_unit_form.html', {'master': master, 'available_units': available_units})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def other_packaging_unit_edit(request, pk, packaging_unit_id):
    master = get_object_or_404(MasterProduct, pk=pk)
    if master.category in ('semi', 'auxiliary', 'tool', 'office'):
        return redirect('product:material_packaging_unit_list', pk=pk)
    if master.category != 'other':
        return redirect('product:product_list')
    conversion = get_object_or_404(
        ItemUnitConversion.objects.select_related('target_unit'),
        pk=packaging_unit_id, content_type='other', master_product=master,
    )
    if request.method == 'POST':
        factor = request.POST.get('factor', '').strip()
        is_default = request.POST.get('is_default') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        remark = request.POST.get('remark', '').strip()
        if not factor:
            messages.error(request, '请填写换算系数')
            return redirect('product:other_packaging_unit_edit', pk=pk, packaging_unit_id=packaging_unit_id)
        try:
            factor_val = Decimal(factor)
            if factor_val <= 0:
                messages.error(request, '换算系数必须大于0')
                return redirect('product:other_packaging_unit_edit', pk=pk, packaging_unit_id=packaging_unit_id)
            conversion.factor = factor_val
            conversion.is_default = is_default
            conversion.is_active = is_active
            conversion.remark = remark
            conversion.save()
            messages.success(request, '换算关系更新成功')
            return redirect('product:other_packaging_unit_list', pk=pk)
        except (ValueError, Exception) as e:
            messages.error(request, f'更新失败：{str(e)}')
    return render(request, 'product/other_packaging_unit_form.html', {'master': master, 'conversion': conversion})


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def other_packaging_unit_delete(request, pk, packaging_unit_id):
    master = get_object_or_404(MasterProduct, pk=pk)
    if master.category in ('semi', 'auxiliary', 'tool', 'office'):
        return redirect('product:material_packaging_unit_list', pk=pk)
    if master.category != 'other':
        return redirect('product:product_list')
    conversion = get_object_or_404(ItemUnitConversion, pk=packaging_unit_id, content_type='other', master_product=master)
    if request.method == 'POST':
        if master.display_unit_id == conversion.target_unit_id:
            messages.error(request, '无法删除：该单位是当前显示单位，请先修改显示单位')
            return redirect('product:other_packaging_unit_list', pk=pk)
        conversion.delete()
        messages.success(request, '换算关系已删除')
        return redirect('product:other_packaging_unit_list', pk=pk)
    return redirect('product:other_packaging_unit_list', pk=pk)


@login_required
@role_or_permission_required('warehouse', 'ceo', permission_code='inventory.unit.manage')
def other_set_display_unit(request, pk, unit_id):
    master = get_object_or_404(MasterProduct, pk=pk)
    if master.category in ('semi', 'auxiliary', 'tool', 'office'):
        return redirect('product:material_set_display_unit', pk=pk, unit_id=unit_id)
    if master.category != 'other':
        return redirect('product:product_list')
    unit = get_object_or_404(Unit, pk=unit_id)
    if request.method == 'POST':
        if unit.pk == master.base_unit_id:
            master.display_unit = unit
            master.save(update_fields=['display_unit'])
            sync_master_to_inventory_other(master)
            messages.success(request, f'显示单位已切换为「{unit.name}」（基础单位）')
        else:
            if not ItemUnitConversion.objects.filter(content_type='other', master_product=master, target_unit=unit, is_active=True).exists():
                messages.error(request, f'「{unit.name}」不在换算表中')
                return redirect('product:other_packaging_unit_list', pk=pk)
            master.display_unit = unit
            master.save(update_fields=['display_unit'])
            sync_master_to_inventory_other(master)
            messages.success(request, f'显示单位已切换为「{unit.name}」')
        return redirect('product:other_packaging_unit_list', pk=pk)
    return redirect('product:other_packaging_unit_list', pk=pk)
