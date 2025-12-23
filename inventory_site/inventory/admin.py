from django.contrib import admin
from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "sku", "name", "category", "quantity", "price", "created_at")
    list_filter = ("category",)
    search_fields = ("sku", "name")
    autocomplete_fields = ("category",)

