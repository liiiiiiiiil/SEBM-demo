from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.paginator import Paginator
from accounts.decorators import role_required
from .models import Shipment, Driver, Vehicle, ShipmentImage
from sales.models import ShippingNotice, SalesOrder
from inventory.models import Inventory, StockTransaction


@login_required
@role_required('logistics', 'ceo')
def shipping_notice_list(request):
    """发货通知单列表"""
    notices = ShippingNotice.objects.select_related('order').filter(status='pending')
    
    # 分页处理
    paginator = Paginator(notices, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'notices': page_obj,
        'extra_params': '',
    }
    return render(request, 'logistics/shipping_notice_list.html', context)


@login_required
@role_required('logistics', 'ceo')
def shipment_create(request, notice_pk):
    """创建发货单"""
    notice = get_object_or_404(ShippingNotice, pk=notice_pk)
    
    if request.method == 'POST':
        driver_id = request.POST.get('driver')
        vehicle_id = request.POST.get('vehicle')
        freight_cost = float(request.POST.get('freight_cost', 0))
        
        if not driver_id:
            messages.error(request, '请选择司机')
            drivers = Driver.objects.prefetch_related('vehicles').all()
            context = {
                'notice': notice,
                'drivers': drivers,
                'vehicles': Vehicle.objects.none(),
            }
            return render(request, 'logistics/shipment_form.html', context)
        
        try:
            driver = Driver.objects.get(pk=driver_id)
        except Driver.DoesNotExist:
            messages.error(request, '选择的司机不存在')
            drivers = Driver.objects.prefetch_related('vehicles').all()
            context = {
                'notice': notice,
                'drivers': drivers,
                'vehicles': Vehicle.objects.none(),
            }
            return render(request, 'logistics/shipment_form.html', context)
        
        vehicle = None
        if vehicle_id:
            try:
                vehicle = Vehicle.objects.get(pk=vehicle_id)
                # 验证车辆是否属于所选司机
                if vehicle not in driver.vehicles.all():
                    messages.error(request, '选择的车辆不属于该司机')
                    drivers = Driver.objects.prefetch_related('vehicles').all()
                    context = {
                        'notice': notice,
                        'drivers': drivers,
                        'vehicles': driver.vehicles.all(),
                        'selected_driver_id': driver_id,
                    }
                    return render(request, 'logistics/shipment_form.html', context)
            except Vehicle.DoesNotExist:
                messages.error(request, '选择的车辆不存在')
                drivers = Driver.objects.prefetch_related('vehicles').all()
                context = {
                    'notice': notice,
                    'drivers': drivers,
                    'vehicles': driver.vehicles.all(),
                    'selected_driver_id': driver_id,
                }
                return render(request, 'logistics/shipment_form.html', context)
        
        with transaction.atomic():
            shipment = Shipment.objects.create(
                shipment_no=f"SH{timezone.now().strftime('%Y%m%d%H%M%S')}",
                shipping_notice=notice,
                order=notice.order,
                driver=driver,
                vehicle=vehicle,
                freight_cost=freight_cost,
                status='loading',
                shipped_by=request.user,
            )
            
            messages.success(request, f'发货单 {shipment.shipment_no} 创建成功')
            return redirect('logistics:shipment_detail', pk=shipment.pk)
    
    drivers = Driver.objects.prefetch_related('vehicles').all()
    
    context = {
        'notice': notice,
        'drivers': drivers,
        'vehicles': Vehicle.objects.none(),
    }
    return render(request, 'logistics/shipment_form.html', context)


@login_required
@role_required('logistics', 'ceo')
def shipment_detail(request, pk):
    """发货单详情"""
    shipment = get_object_or_404(Shipment.objects.select_related('order', 'driver', 'vehicle'), pk=pk)
    
    # 获取发货回执图片
    images = ShipmentImage.objects.filter(shipment=shipment).select_related('uploaded_by').order_by('-uploaded_at')
    
    context = {
        'shipment': shipment,
        'images': images,
    }
    return render(request, 'logistics/shipment_detail.html', context)


@login_required
@role_required('logistics', 'ceo')
def shipment_ship(request, pk):
    """确认发货"""
    shipment = get_object_or_404(Shipment, pk=pk)
    
    if shipment.status != 'loading':
        messages.error(request, '发货单状态不正确')
        return redirect('logistics:shipment_detail', pk=pk)
    
    if request.method == 'POST':
        with transaction.atomic():
            from inventory.models import Batch
            from sales.models import SalesOrderItemBatch
            from decimal import Decimal
            # 扣减成品库存（按批次）
            for item in shipment.order.items.all():
                inventory = Inventory.objects.get(inventory_type='product', product=item.product)
                remaining_qty = item.quantity
                
                # 首先从订单中获取已保存的批次分配作为默认值
                batch_allocations = {}
                order_batch_allocations = SalesOrderItemBatch.objects.filter(order_item=item)
                for order_batch in order_batch_allocations:
                    if order_batch.batch.quantity > 0:
                        # 使用订单中保存的分配数量，但不超过当前可用数量
                        allocate_qty = min(order_batch.quantity, order_batch.batch.quantity)
                        if allocate_qty > 0:
                            batch_allocations[order_batch.batch.id] = allocate_qty
                
                # 然后从表单获取用户调整后的数量（以订单分配为指导，但允许调整）
                for batch in inventory.get_batches().filter(quantity__gt=0).order_by('batch_date', 'created_at'):
                    batch_qty_key = f'batch_quantity_{item.product.id}_{batch.id}'
                    batch_qty_str = request.POST.get(batch_qty_key, '')
                    if batch_qty_str:
                        try:
                            batch_qty = Decimal(batch_qty_str)
                            if batch_qty > 0 and batch_qty <= batch.quantity:
                                # 使用表单中提交的数量（用户可能调整了订单中的分配）
                                batch_allocations[batch.id] = batch_qty
                        except:
                            pass
                
                # 重新计算已分配总量
                total_allocated = sum(batch_allocations.values())
                remaining_qty = item.quantity - total_allocated
                
                # 如果仍然不足，使用FIFO自动分配
                if remaining_qty > 0:
                    for batch in inventory.get_batches().filter(quantity__gt=0).order_by('batch_date', 'created_at'):
                        if remaining_qty <= 0:
                            break
                        available = batch.quantity - batch_allocations.get(batch.id, 0)
                        if available > 0:
                            allocate_qty = min(remaining_qty, available)
                            batch_allocations[batch.id] = batch_allocations.get(batch.id, 0) + allocate_qty
                            remaining_qty -= allocate_qty
                
                # 按批次扣减库存
                for batch_id, batch_qty in batch_allocations.items():
                    if batch_qty > 0:
                        batch = Batch.objects.get(pk=batch_id)
                        batch.quantity -= batch_qty
                        batch.save()
                
                # 记录库存变动
                StockTransaction.objects.create(
                    transaction_type='sale_out',
                    inventory=inventory,
                            batch=batch,
                            quantity=batch_qty,
                    unit=item.product.unit,
                    reference_no=shipment.shipment_no,
                    operator=request.user,
                )
                
                # 更新库存总数量
                inventory.update_quantity_from_batches()
            
            shipment.status = 'shipped'
            shipment.shipped_at = timezone.now()
            shipment.save()
            
            shipment.shipping_notice.status = 'shipped'
            shipment.shipping_notice.save()
            
            # 发货后订单状态保持为'已发货'，不直接变为'已完成'
            shipment.order.status = 'shipped'
            shipment.order.save()
            
            messages.success(request, f'发货单 {shipment.shipment_no} 已发货，待客户收货后请补充发货回执')
            return redirect('logistics:shipment_detail', pk=pk)
    
    # 获取每个产品的可用批次，构建更友好的数据结构
    from sales.models import SalesOrderItemBatch
    order_items_with_batches = []
    for item in shipment.order.items.all():
        try:
            inventory = Inventory.objects.get(inventory_type='product', product=item.product)
            batches = inventory.get_batches().filter(quantity__gt=0).order_by('batch_date', 'created_at')
        except Inventory.DoesNotExist:
            batches = []
        
        # 获取订单中已保存的批次分配
        order_batch_allocations = {}
        for order_batch in SalesOrderItemBatch.objects.filter(order_item=item):
            order_batch_allocations[order_batch.batch.id] = float(order_batch.quantity)
        
        order_items_with_batches.append({
            'item': item,
            'batches': batches,
            'order_batch_allocations': order_batch_allocations,
        })
    
    context = {
        'shipment': shipment,
        'order_items_with_batches': order_items_with_batches,
    }
    return render(request, 'logistics/shipment_ship.html', context)


@login_required
@role_required('logistics', 'ceo')
def driver_list(request):
    """司机列表"""
    drivers = Driver.objects.prefetch_related('vehicles').all()
    
    # 分页处理
    paginator = Paginator(drivers, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'logistics/driver_list.html', {
        'drivers': page_obj,
        'extra_params': '',
    })


@login_required
@role_required('logistics', 'ceo')
def driver_create(request):
    """创建司机"""
    from decimal import Decimal, InvalidOperation
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        license_no = request.POST.get('license_no', '').strip()
        license_type = request.POST.get('license_type', '').strip()
        
        if not name:
            messages.error(request, '请输入司机姓名')
            return redirect('logistics:driver_create')
        
        if not phone:
            messages.error(request, '请输入联系方式')
            return redirect('logistics:driver_create')
        
        try:
            with transaction.atomic():
                driver = Driver.objects.create(
                    name=name,
                    phone=phone,
                    license_no=license_no if license_no else None,
                    license_type=license_type,
                )
                
                # 处理车辆数据
                vehicle_count = 0
                i = 0
                while True:
                    plate_no = request.POST.get(f'vehicle_plate_no_{i}', '').strip()
                    if not plate_no:
                        break
                    
                    vehicle_type = request.POST.get(f'vehicle_type_{i}', '').strip()
                    model = request.POST.get(f'vehicle_model_{i}', '').strip()
                    capacity_str = request.POST.get(f'vehicle_capacity_{i}', '').strip()
                    
                    if not vehicle_type:
                        i += 1
                        continue
                    
                    capacity = None
                    if capacity_str:
                        try:
                            capacity = Decimal(capacity_str)
                        except (InvalidOperation, ValueError):
                            pass
                    
                    if not plate_no:
                        continue
                    
                    Vehicle.objects.create(
                        driver=driver,
                        plate_no=plate_no,
                        vehicle_type=vehicle_type,
                        model=model,
                        capacity=capacity,
                    )
                    vehicle_count += 1
                    i += 1
                
                messages.success(request, f'司机 {driver.name} 创建成功，已添加 {vehicle_count} 辆车')
                return redirect('logistics:driver_list')
        except Exception as e:
            messages.error(request, f'创建失败：{str(e)}')
            return redirect('logistics:driver_create')
    
    context = {
        'title': '创建司机',
    }
    return render(request, 'logistics/driver_form.html', context)


@login_required
@role_required('logistics', 'ceo')
def driver_edit(request, pk):
    """编辑司机"""
    from decimal import Decimal, InvalidOperation
    
    driver = get_object_or_404(Driver.objects.prefetch_related('vehicles'), pk=pk)
    
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        phone = request.POST.get('phone', '').strip()
        license_no = request.POST.get('license_no', '').strip()
        license_type = request.POST.get('license_type', '').strip()
        
        if not name:
            messages.error(request, '请输入司机姓名')
            return redirect('logistics:driver_edit', pk=pk)
        
        if not phone:
            messages.error(request, '请输入联系方式')
            return redirect('logistics:driver_edit', pk=pk)
        
        try:
            with transaction.atomic():
                driver.name = name
                driver.phone = phone
                driver.license_no = license_no if license_no else None
                driver.license_type = license_type
                driver.save()
                
                # 处理车辆数据：先删除现有车辆，再创建新的
                driver.vehicles.all().delete()
                
                vehicle_count = 0
                i = 0
                while True:
                    plate_no = request.POST.get(f'vehicle_plate_no_{i}', '').strip()
                    if not plate_no:
                        break
                    
                    vehicle_type = request.POST.get(f'vehicle_type_{i}', '').strip()
                    model = request.POST.get(f'vehicle_model_{i}', '').strip()
                    capacity_str = request.POST.get(f'vehicle_capacity_{i}', '').strip()
                    
                    if not vehicle_type:
                        i += 1
                        continue
                    
                    capacity = None
                    if capacity_str:
                        try:
                            capacity = Decimal(capacity_str)
                        except (InvalidOperation, ValueError):
                            pass
                    
                    if not plate_no:
                        continue
                    
                    Vehicle.objects.create(
                        driver=driver,
                        plate_no=plate_no,
                        vehicle_type=vehicle_type,
                        model=model,
                        capacity=capacity,
                    )
                    vehicle_count += 1
                    i += 1
                
                messages.success(request, f'司机 {driver.name} 更新成功，已更新 {vehicle_count} 辆车')
                return redirect('logistics:driver_list')
        except Exception as e:
            messages.error(request, f'更新失败：{str(e)}')
            return redirect('logistics:driver_edit', pk=pk)
    
    vehicles = list(driver.vehicles.all())
    context = {
        'driver': driver,
        'vehicles': vehicles,
        'title': '编辑司机',
    }
    return render(request, 'logistics/driver_form.html', context)


@login_required
@role_required('logistics', 'ceo')
def driver_delete(request, pk):
    """删除司机"""
    driver = get_object_or_404(Driver, pk=pk)
    
    if request.method == 'POST':
        driver_name = driver.name
        driver.delete()
        messages.success(request, f'司机 {driver_name} 已删除')
        return redirect('logistics:driver_list')
    
    return render(request, 'logistics/driver_confirm_delete.html', {'driver': driver})


@login_required
@role_required('logistics', 'ceo')
def shipment_list(request):
    """发货单列表（包括所有状态和待发货通知单）"""
    # 获取所有发货单
    shipments = Shipment.objects.select_related('order', 'driver', 'vehicle', 'shipped_by').all()
    
    # 获取所有待发货通知单（还没有创建发货单的）
    pending_notices = ShippingNotice.objects.select_related('order').filter(
        status='pending'
    ).exclude(
        id__in=Shipment.objects.values_list('shipping_notice_id', flat=True)
    )
    
    # 状态筛选
    status_filter = request.GET.get('status', '')
    if status_filter:
        if status_filter == 'pending':
            # 筛选时，只显示待发货通知单
            shipments = Shipment.objects.none()
            pending_notices = pending_notices
        else:
            # 其他状态筛选发货单
            shipments = shipments.filter(status=status_filter)
            pending_notices = ShippingNotice.objects.none()
    
    # 合并发货单和待发货通知单用于分页
    all_items = list(shipments) + list(pending_notices)
    # 按创建时间倒序排序
    all_items.sort(key=lambda x: x.created_at if hasattr(x, 'created_at') else x.order.created_at, reverse=True)
    
    # 分页处理
    paginator = Paginator(all_items, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 构建额外参数用于分页链接
    extra_params = ''
    if status_filter:
        extra_params = f'status={status_filter}'
    
    context = {
        'page_obj': page_obj,
        'shipments': shipments,
        'pending_notices': pending_notices,
        'status_filter': status_filter,
        'extra_params': extra_params,
    }
    return render(request, 'logistics/shipment_list.html', context)


@login_required
@role_required('logistics', 'ceo')
def shipment_delivery_confirm(request, pk):
    """发货回执确认"""
    shipment = get_object_or_404(Shipment.objects.select_related('order'), pk=pk)
    
    if shipment.status != 'shipped':
        messages.error(request, '只能对已发货的发货单进行回执确认')
        return redirect('logistics:shipment_detail', pk=pk)
    
    if request.method == 'POST':
        receiver_name = request.POST.get('receiver_name', '').strip()
        receiver_phone = request.POST.get('receiver_phone', '').strip()
        delivery_remark = request.POST.get('delivery_remark', '').strip()
        
        if not receiver_name:
            messages.error(request, '请输入收货人姓名')
            return render(request, 'logistics/shipment_delivery_confirm.html', {'shipment': shipment})
        
        with transaction.atomic():
            shipment.status = 'delivered'
            shipment.delivered_by = request.user
            shipment.delivered_at = timezone.now()
            shipment.receiver_name = receiver_name
            shipment.receiver_phone = receiver_phone
            shipment.delivery_remark = delivery_remark
            shipment.save()
            
            # 处理上传的图片
            if 'images' in request.FILES:
                images = request.FILES.getlist('images')
                image_remarks = request.POST.getlist('image_remark')
                
                for i, image in enumerate(images):
                    if image:
                        remark = image_remarks[i] if i < len(image_remarks) else ''
                        ShipmentImage.objects.create(
                            shipment=shipment,
                            image=image,
                            uploaded_by=request.user,
                            remark=remark,
                        )
            
            # 检查订单的所有发货单是否都已送达
            all_shipments_delivered = all(
                s.status == 'delivered' 
                for s in Shipment.objects.filter(order=shipment.order)
            )
            
            # 如果所有发货单都已送达，订单状态变为已完成
            if all_shipments_delivered:
                shipment.order.status = 'completed'
                shipment.order.save()
            
            messages.success(request, f'发货单 {shipment.shipment_no} 回执确认成功，订单流程已完成')
            return redirect('logistics:shipment_detail', pk=pk)
    
    return render(request, 'logistics/shipment_delivery_confirm.html', {'shipment': shipment})


@login_required
@role_required('logistics', 'ceo')
def vehicle_list(request):
    """车辆列表"""
    vehicles = Vehicle.objects.all()
    
    # 分页处理
    paginator = Paginator(vehicles, 20)  # 每页20条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'logistics/vehicle_list.html', {
        'vehicles': page_obj,
        'extra_params': '',
    })
