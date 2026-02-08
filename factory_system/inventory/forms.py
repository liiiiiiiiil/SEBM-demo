from django import forms
from .models import Product, ProductCategory, Material, MaterialCategory, InventoryAdjustmentRequest, Unit


class ProductForm(forms.ModelForm):
    """成品表单 — 双单位体系重构后，使用 base_unit / display_unit 替代旧 unit CharField"""
    class Meta:
        model = Product
        fields = ['sku', 'name', 'category', 'specification', 'unit_price', 'sale_price', 'safety_stock', 'base_unit', 'display_unit']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'specification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'sale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
            'display_unit': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 只显示启用的单位
        active_units = Unit.objects.filter(is_active=True)
        self.fields['base_unit'].queryset = active_units
        self.fields['display_unit'].queryset = active_units
        # 如果是编辑已有产品且有关联数据，基础单位不可修改
        if self.instance and self.instance.pk:
            from .models import Inventory, BOM
            has_data = (
                Inventory.objects.filter(product=self.instance).exists()
                or BOM.objects.filter(product=self.instance).exists()
            )
            if has_data:
                self.fields['base_unit'].disabled = True
                self.fields['base_unit'].help_text = '已有关联数据，不可修改基础单位'


class MaterialForm(forms.ModelForm):
    """原料表单"""
    class Meta:
        model = Material
        fields = ['sku', 'name', 'category', 'material_type', 'base_unit', 'display_unit', 'unit_price', 'safety_stock']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'material_type': forms.Select(attrs={'class': 'form-select'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
            'display_unit': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_units = Unit.objects.filter(is_active=True)
        self.fields['base_unit'].queryset = active_units
        self.fields['display_unit'].queryset = active_units
        if self.instance and self.instance.pk:
            from .models import Inventory, BOM
            has_data = (
                Inventory.objects.filter(material=self.instance).exists()
                or BOM.objects.filter(material=self.instance).exists()
            )
            if has_data:
                self.fields['base_unit'].disabled = True
                self.fields['base_unit'].help_text = '已有关联数据，不可修改基础单位'


class InventoryAdjustmentRequestForm(forms.ModelForm):
    """库存调整申请表单 — 双单位体系重构后，移除「单位调整」类型"""
    ADJUSTMENT_TYPE_CHOICES = [
        ('quantity', '数量调整'),
        ('price', '单价调整'),
    ]
    
    adjustment_type = forms.ChoiceField(
        choices=ADJUSTMENT_TYPE_CHOICES,
        initial='quantity',
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        label='调整类型',
        required=True,
    )
    
    class Meta:
        model = InventoryAdjustmentRequest
        fields = ['adjustment_type', 'adjust_quantity', 'adjust_unit_price', 'reason']
        widgets = {
            'adjust_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'adjust_unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'required': True}),
        }
        labels = {
            'adjust_quantity': '调整数量（基础单位）',
            'adjust_unit_price': '调整单价（基础单位）',
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
        
        if adjustment_type == 'quantity':
            if adjust_quantity is None:
                raise forms.ValidationError('数量调整需要填写调整数量')
        
        if adjustment_type == 'price':
            if adjust_unit_price is None:
                raise forms.ValidationError('单价调整需要填写调整单价')
        
        if adjustment_type == 'quantity' and adjust_unit_price is not None:
            raise forms.ValidationError('数量调整时，不应填写单价')
        
        if adjustment_type == 'price' and adjust_quantity is not None:
            raise forms.ValidationError('单价调整时，不应填写数量')
        
        return cleaned_data
