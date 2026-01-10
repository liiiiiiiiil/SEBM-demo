from django.db import models
from sales.models import SalesOrder, ShippingNotice


class Driver(models.Model):
    """司机信息"""
    name = models.CharField(max_length=100, verbose_name='姓名')
    phone = models.CharField(max_length=20, verbose_name='联系电话')
    license_no = models.CharField(max_length=50, unique=True, verbose_name='驾照号码')
    license_type = models.CharField(max_length=20, verbose_name='驾照类型')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '司机'
        verbose_name_plural = '司机'
    
    def __str__(self):
        return f"{self.name} - {self.license_no}"


class Vehicle(models.Model):
    """车辆信息"""
    VEHICLE_TYPE_CHOICES = [
        ('truck', '货车'),
        ('van', '面包车'),
        ('pickup', '皮卡'),
    ]
    
    plate_no = models.CharField(max_length=20, unique=True, verbose_name='车牌号')
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPE_CHOICES, verbose_name='车辆类型')
    model = models.CharField(max_length=100, verbose_name='车型')
    capacity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='载重(吨)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        verbose_name = '车辆'
        verbose_name_plural = '车辆'
    
    def __str__(self):
        return f"{self.plate_no} - {self.get_vehicle_type_display()}"


class Shipment(models.Model):
    """发货单"""
    STATUS_CHOICES = [
        ('pending', '待发货'),
        ('loading', '装车中'),
        ('shipped', '已发货'),
        ('delivered', '已送达'),
    ]
    
    shipment_no = models.CharField(max_length=50, unique=True, verbose_name='发货单号')
    shipping_notice = models.ForeignKey(ShippingNotice, on_delete=models.CASCADE, related_name='shipments', verbose_name='发货通知单')
    order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name='shipments', verbose_name='订单')
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, null=True, blank=True, verbose_name='司机')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, null=True, blank=True, verbose_name='车辆')
    freight_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='运费')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name='状态')
    shipped_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='shipped_shipments', verbose_name='发货人')
    shipped_at = models.DateTimeField(null=True, blank=True, verbose_name='发货时间')
    # 发货回执相关字段
    delivered_by = models.ForeignKey('auth.User', on_delete=models.PROTECT, null=True, blank=True, related_name='delivered_shipments', verbose_name='回执录入人')
    delivered_at = models.DateTimeField(null=True, blank=True, verbose_name='收货时间')
    receiver_name = models.CharField(max_length=100, blank=True, verbose_name='收货人姓名')
    receiver_phone = models.CharField(max_length=20, blank=True, verbose_name='收货人电话')
    delivery_remark = models.TextField(blank=True, verbose_name='回执备注')
    remark = models.TextField(blank=True, verbose_name='备注')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        verbose_name = '发货单'
        verbose_name_plural = '发货单'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.shipment_no} - {self.order.order_no} - {self.get_status_display()}"
