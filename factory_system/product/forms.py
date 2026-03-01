# 产品主数据表单（product.Product）
from django import forms
from .models import Product
from inventory.models import Unit


class ProductCreateForm(forms.ModelForm):
    """统一创建表单：创建时选择类别（成品/原料/其他）；仅定义基础单位，显示单位未填时默认等于基础单位"""
    class Meta:
        model = Product
        fields = ['category', 'sku', 'name', 'base_unit', 'unit_price', 'safety_stock']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        initial_category = kwargs.pop('initial_category', None)
        super().__init__(*args, **kwargs)
        self.fields['category'].choices = Product.CATEGORY_CHOICES
        qs = Unit.objects.filter(is_active=True)
        self.fields['base_unit'].queryset = qs
        if initial_category:
            self.fields['category'].initial = initial_category


class ProductMasterForm(forms.ModelForm):
    """产品主数据表单（成品：category=finished）；仅基础单位，显示单位未填时默认等于基础单位"""
    class Meta:
        model = Product
        fields = ['sku', 'name', 'base_unit', 'unit_price', 'safety_stock']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Unit.objects.filter(is_active=True)
        self.fields['base_unit'].queryset = qs


class MaterialMasterForm(forms.ModelForm):
    """产品主数据表单（原料：category=raw）；仅基础单位，显示单位未填时默认等于基础单位"""
    class Meta:
        model = Product
        fields = ['sku', 'name', 'unit_price', 'safety_stock', 'base_unit']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Unit.objects.filter(is_active=True)
        self.fields['base_unit'].queryset = qs


class OtherMasterForm(forms.ModelForm):
    """产品主数据表单（其它：category=other）；仅基础单位，显示单位未填时默认等于基础单位"""
    class Meta:
        model = Product
        fields = ['sku', 'name', 'unit_price', 'safety_stock', 'base_unit']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Unit.objects.filter(is_active=True)
        self.fields['base_unit'].queryset = qs


class ProductEditForm(forms.ModelForm):
    """编辑产品主数据时可修改类型（category）及基本信息；类型变更后会自动同步到库存对应表"""
    class Meta:
        model = Product
        fields = ['category', 'sku', 'name', 'base_unit', 'unit_price', 'safety_stock']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'base_unit': forms.Select(attrs={'class': 'form-select'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].choices = Product.CATEGORY_CHOICES
        qs = Unit.objects.filter(is_active=True)
        self.fields['base_unit'].queryset = qs
