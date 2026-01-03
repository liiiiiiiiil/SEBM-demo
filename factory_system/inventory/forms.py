from django import forms
from .models import Customer


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

