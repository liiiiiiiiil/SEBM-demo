from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from accounts.decorators import role_required
from .models import Shipment, Driver, Vehicle
from sales.models import ShippingNotice, SalesOrder
from inventory.models import Inventory, StockTransaction


@login_required
@role_required('logistics', 'ceo')
def shipping_notice_list(request):
    """发货通知单列表"""
    notices = ShippingNotice.objects.select_related('order').filter(status='pending')
    
    context = {
        'notices': notices,
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
        
        driver = Driver.objects.get(pk=driver_id) if driver_id else None
        vehicle = Vehicle.objects.get(pk=vehicle_id) if vehicle_id else None
        
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
    
    drivers = Driver.objects.all()
    vehicles = Vehicle.objects.all()
    
    context = {
        'notice': notice,
        'drivers': drivers,
        'vehicles': vehicles,
    }
    return render(request, 'logistics/shipment_form.html', context)


@login_required
@role_required('logistics', 'ceo')
def shipment_detail(request, pk):
    """发货单详情"""
    shipment = get_object_or_404(Shipment.objects.select_related('order', 'driver', 'vehicle'), pk=pk)
    
    context = {
        'shipment': shipment,
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
            # 扣减成品库存
            for item in shipment.order.items.all():
                inventory = Inventory.objects.get(inventory_type='product', product=item.product)
                inventory.quantity -= item.quantity
                inventory.save()
                
                # 记录库存变动
                StockTransaction.objects.create(
                    transaction_type='sale_out',
                    inventory=inventory,
                    quantity=item.quantity,
                    unit=item.product.unit,
                    reference_no=shipment.shipment_no,
                    operator=request.user,
                )
            
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
    
    return render(request, 'logistics/shipment_ship.html', {'shipment': shipment})


@login_required
@role_required('logistics', 'ceo')
def driver_list(request):
    """司机列表"""
    drivers = Driver.objects.all()
    return render(request, 'logistics/driver_list.html', {'drivers': drivers})


@login_required
@role_required('logistics', 'ceo')
def shipment_list(request):
    """发货单列表（包括所有状态）"""
    shipments = Shipment.objects.select_related('order', 'driver', 'vehicle', 'shipped_by').all()
    
    # 状态筛选
    status_filter = request.GET.get('status', '')
    if status_filter:
        shipments = shipments.filter(status=status_filter)
    
    context = {
        'shipments': shipments,
        'status_filter': status_filter,
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
    return render(request, 'logistics/vehicle_list.html', {'vehicles': vehicles})
