from django import forms
from .models import SalesOrder, SalesOrderItem
from inventory.models import Customer, Product


class SalesOrderItemForm(forms.ModelForm):
    class Meta:
        model = SalesOrderItem
        fields = ['product', 'quantity', 'unit_price']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


SalesOrderItemFormSet = forms.inlineformset_factory(
    SalesOrder,
    SalesOrderItem,
    form=SalesOrderItemForm,
    extra=1,
    can_delete=True,
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

