from django import forms
from .models import SalesOrder, SalesOrderItem, Customer
from inventory.models import Product


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ['name', 'contact_person', 'phone', 'address', 'credit_level']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'credit_level': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'name': '客户名称',
            'contact_person': '联系人',
            'phone': '联系电话',
            'address': '地址',
            'credit_level': '信用等级',
        }


class SalesOrderItemForm(forms.ModelForm):
    class Meta:
        model = SalesOrderItem
        fields = ['product', 'quantity', 'unit_price', 'manual_batch_allocation']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'manual_batch_allocation': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 自定义产品选择框，仅显示产品名称
        products = Product.objects.all()
        choices = [('', '---------')]
        for product in products:
            choices.append((product.id, product.name))
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

