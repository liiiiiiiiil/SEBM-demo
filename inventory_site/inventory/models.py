from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        verbose_name = "分类"
        verbose_name_plural = "分类"

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    sku = models.CharField("SKU", max_length=50, unique=True)
    name = models.CharField("名称", max_length=200)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products", verbose_name="分类"
    )
    quantity = models.PositiveIntegerField("数量", default=0)
    price = models.DecimalField("价格", max_digits=10, decimal_places=2)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "产品"
        verbose_name_plural = "产品"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"

