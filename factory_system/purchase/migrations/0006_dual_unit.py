# 双单位系统迁移 - purchase 应用
# 移除旧的 unit CharField，添加 display_unit 和 display_quantity

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('purchase', '0005_remove_purchasetaskitem_received_quantity'),
        ('inventory', '0022_dual_unit_phase2'),  # 确保 inventory 迁移完成
    ]

    operations = [
        # 移除 PurchaseTaskItem.unit（旧的 CharField）
        migrations.RemoveField(
            model_name='purchasetaskitem',
            name='unit',
        ),
        # 添加 display_unit FK（可选，记录采购时使用的单位）
        migrations.AddField(
            model_name='purchasetaskitem',
            name='display_unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='purchase_items',
                to='inventory.unit',
                verbose_name='采购单位',
            ),
        ),
        # 添加 display_quantity（可选，记录采购时的原始数量）
        migrations.AddField(
            model_name='purchasetaskitem',
            name='display_quantity',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='采购数量（采购单位）',
            ),
        ),
    ]
