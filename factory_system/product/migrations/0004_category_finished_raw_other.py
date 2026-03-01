# 产品管理分类统一为：成品、原料、其他（半成品/其它归入其他）
from django.db import migrations


def merge_category_to_other(apps, schema_editor):
    Product = apps.get_model('product', 'Product')
    Product.objects.filter(category__in=('semi', 'other')).update(category='other')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [('product', '0003_data_from_inventory')]
    operations = [
        migrations.RunPython(merge_category_to_other, noop),
    ]
