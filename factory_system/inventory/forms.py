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
        fields = ['sku', 'name', 'category', 'specification', 'sale_price', 'safety_stock', 'unit']
        widgets = {
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'specification': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'sale_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'safety_stock': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
        }


class InventoryAdjustmentRequestForm(forms.ModelForm):
    class Meta:
        model = InventoryAdjustmentRequest
        fields = ['adjust_quantity', 'reason']
        widgets = {
            'adjust_quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'required': True}),
        }
        labels = {
            'adjust_quantity': '调整数量',
            'reason': '调整原因',
        }


