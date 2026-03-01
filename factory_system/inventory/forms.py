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
    """库存调整申请表单 — 仅支持数量调整；单价/单位调整请到「产品管理」模块"""
    adjustment_type = forms.CharField(
        initial='quantity',
        widget=forms.HiddenInput(),
        required=True,
    )

    class Meta:
        model = InventoryAdjustmentRequest
        fields = ['adjustment_type', 'adjust_quantity', 'reason']
        widgets = {
            'adjust_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'required': True}),
        }
        labels = {
            'adjust_quantity': '调整数量（基础单位）',
            'reason': '调整原因',
        }

    def clean(self):
        cleaned_data = super().clean()
        adjust_quantity = cleaned_data.get('adjust_quantity')
        if adjust_quantity is None:
            raise forms.ValidationError('请填写调整数量（正数增加、负数减少）')
        return cleaned_data
