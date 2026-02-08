# 为 Inventory 的「其它」类型添加 other_unit 字段

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0022_dual_unit_phase2'),
    ]

    operations = [
        migrations.AddField(
            model_name='inventory',
            name='other_unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='other_inventories',
                to='inventory.unit',
                verbose_name='其它物品单位',
            ),
        ),
    ]
