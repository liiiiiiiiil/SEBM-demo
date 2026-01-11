from django import forms
from .models import Customer, Product, ProductCategory, Material, MaterialCategory, InventoryAdjustmentRequest


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


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['sku', 'name', 'category', 'specification', 'unit_price', 'sale_price', 'safety_stock', 'unit']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'specification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'sale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
        }


class InventoryAdjustmentRequestForm(forms.ModelForm):
    ADJUSTMENT_TYPE_CHOICES = [
        ('quantity', '仅调整数量'),
        ('price', '仅调整单价'),
        ('both', '同时调整数量和单价'),
    ]
    
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPE_CHOICES,
        initial='quantity',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='调整类型',
        required=True
    )
    
    class Meta:
        model = InventoryAdjustmentRequest
        fields = ['adjust_quantity', 'adjust_unit_price', 'reason']
        widgets = {
            'adjust_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'adjust_unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'required': True}),
        }
        labels = {
            'adjust_quantity': '调整数量',
            'adjust_unit_price': '调整单价',
            'reason': '调整原因',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['adjust_quantity'].required = False
        self.fields['adjust_unit_price'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        adjustment_type = cleaned_data.get('adjustment_type')
        adjust_quantity = cleaned_data.get('adjust_quantity')
        adjust_unit_price = cleaned_data.get('adjust_unit_price')
        
        if adjustment_type == 'quantity' or adjustment_type == 'both':
            if adjust_quantity is None:
                raise forms.ValidationError('数量调整类型需要填写调整数量')
        
        if adjustment_type == 'price' or adjustment_type == 'both':
            if adjust_unit_price is None:
                raise forms.ValidationError('单价调整类型需要填写调整单价')
        
        if adjustment_type == 'quantity' and adjust_unit_price is not None:
            raise forms.ValidationError('仅调整数量时，不应填写单价')
        
        if adjustment_type == 'price' and adjust_quantity is not None:
            raise forms.ValidationError('仅调整单价时，不应填写数量')
        
        return cleaned_data


