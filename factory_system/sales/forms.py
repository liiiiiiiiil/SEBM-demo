from django import forms
from .models import SalesOrder, SalesOrderItem
from inventory.models import Customer, Product, Inventory


class SalesOrderItemForm(forms.ModelForm):
    class Meta:
        model = SalesOrderItem
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自定义产品选择框，在下拉选项中显示库存数量和基础单价
        products = Product.objects.all()
        choices = [('', '---------')]
        
        for product in products:
            try:
                inventory = Inventory.objects.get(inventory_type='product', product=product)
                quantity = float(inventory.quantity)
                unit = inventory.unit
            except Inventory.DoesNotExist:
                quantity = 0.0
                unit = product.unit
            
            # 获取基础单价
            unit_price = float(product.unit_price) if product.unit_price else 0.0
            
            # 在选项文本中显示库存数量和基础单价，便于销售预判
            if quantity <= 0:
                display_text = f"{product.name} (库存: {quantity}{unit} - 缺货 | 基础单价: ¥{unit_price:.2f})"
            else:
                display_text = f"{product.name} (库存: {quantity}{unit} | 基础单价: ¥{unit_price:.2f})"
            
            choices.append((product.id, display_text))
        
        self.fields['product'].widget.choices = choices


# 默认formset（用于新建订单，extra=1显示一个空行）
# 注意：不要设置min_num，否则会和extra叠加导致多出空行
SalesOrderItemFormSet = forms.inlineformset_factory(
    SalesOrder,
    SalesOrderItem,
    form=SalesOrderItemForm,
    extra=1,
    can_delete=True,
)

# 编辑订单时的formset（extra=0，不显示空行）
SalesOrderItemFormSetEdit = forms.inlineformset_factory(
    SalesOrder,
    SalesOrderItem,
    form=SalesOrderItemForm,
    extra=0,
    can_delete=True,
    min_num=1,  # 编辑时至少需要1个明细
    validate_min=True,
)


class SalesOrderForm(forms.ModelForm):
    class Meta:
        model = SalesOrder
        fields = ['customer', 'reserve_inventory', 'remark']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-control'}),
            'reserve_inventory': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'remark': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

