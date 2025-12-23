from django.shortcuts import get_object_or_404, redirect, render
from .forms import ProductForm
from .models import Product


def product_list(request):
    query = request.GET.get("q", "")
    qs = Product.objects.select_related("category")
    if query:
        qs = qs.filter(name__icontains=query)
    products = qs
    return render(
        request,
        "inventory/product_list.html",
        {"products": products, "q": query},
    )


def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("product_list")
    else:
        form = ProductForm()
    return render(request, "inventory/product_form.html", {"form": form, "title": "新增产品"})


def product_update(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            form.save()
            return redirect("product_list")
    else:
        form = ProductForm(instance=product)
    return render(request, "inventory/product_form.html", {"form": form, "title": "编辑产品"})


def product_delete(request, pk: int):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        product.delete()
        return redirect("product_list")
    return render(request, "inventory/product_confirm_delete.html", {"product": product})

