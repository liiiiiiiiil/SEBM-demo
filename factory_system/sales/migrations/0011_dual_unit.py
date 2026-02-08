# 双单位系统迁移 - sales 应用
# 添加 display_unit 和 display_quantity 字段

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0010_customer_alter_salesorder_customer_customertransfer_and_more'),
        ('inventory', '0022_dual_unit_phase2'),  # 确保 inventory 迁移完成
    ]

    operations = [
        # 添加 SalesOrderItem.display_unit FK（可选，记录销售时使用的单位）
        migrations.AddField(
            model_name='salesorderitem',
            name='display_unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='sales_items',
                to='inventory.unit',
                verbose_name='销售单位',
            ),
        ),
        # 添加 SalesOrderItem.display_quantity（可选，记录销售时的原始数量）
        migrations.AddField(
            model_name='salesorderitem',
            name='display_quantity',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='销售数量（销售单位）',
            ),
        ),
    ]
