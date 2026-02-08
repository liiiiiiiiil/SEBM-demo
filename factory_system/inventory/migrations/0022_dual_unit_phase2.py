# 双单位系统迁移 - 阶段3：清理旧字段、设置约束
# 数据已迁移完成，现在可以安全地移除旧字段并设置 NOT NULL 约束

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0021_dual_unit_data'),
    ]

    operations = [
        # ========== Material 最终化 ==========
        # base_unit 设为 NOT NULL（数据已填充）
        migrations.AlterField(
            model_name='material',
            name='base_unit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='base_unit_materials',
                to='inventory.unit',
                verbose_name='基础单位',
            ),
        ),
        # display_unit 设为 NOT NULL
        migrations.AlterField(
            model_name='material',
            name='display_unit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='display_unit_materials',
                to='inventory.unit',
                verbose_name='显示单位',
            ),
        ),
        # 移除旧的 unit CharField
        migrations.RemoveField(
            model_name='material',
            name='unit',
        ),

        # ========== Product 最终化 ==========
        migrations.AlterField(
            model_name='product',
            name='base_unit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='base_unit_products',
                to='inventory.unit',
                verbose_name='基础单位',
            ),
        ),
        migrations.AlterField(
            model_name='product',
            name='display_unit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='display_unit_products',
                to='inventory.unit',
                verbose_name='显示单位',
            ),
        ),
        migrations.RemoveField(
            model_name='product',
            name='unit',
        ),

        # ========== BOM 最终化 ==========
        migrations.AlterField(
            model_name='bom',
            name='unit',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='bom_items',
                to='inventory.unit',
                verbose_name='用量单位',
            ),
        ),

        # ========== StockTransaction 最终化 ==========
        # 移除 unit_legacy（旧 CharField）
        migrations.RemoveField(
            model_name='stocktransaction',
            name='unit_legacy',
        ),
        # 移除 old_unit_price 和 new_unit_price
        migrations.RemoveField(
            model_name='stocktransaction',
            name='old_unit_price',
        ),
        migrations.RemoveField(
            model_name='stocktransaction',
            name='new_unit_price',
        ),
        # base_quantity 设置默认值并改为 NOT NULL
        migrations.AlterField(
            model_name='stocktransaction',
            name='base_quantity',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=10,
                verbose_name='基础单位数量',
            ),
        ),

        # ========== Inventory 清理 ==========
        # 移除 unit CharField
        migrations.RemoveField(
            model_name='inventory',
            name='unit',
        ),

        # ========== InventoryAdjustmentRequest 清理 ==========
        migrations.RemoveField(
            model_name='inventoryadjustmentrequest',
            name='new_unit',
        ),
        migrations.RemoveField(
            model_name='inventoryadjustmentrequest',
            name='conversion_factor',
        ),

        # ========== 删除旧模型 ==========
        migrations.DeleteModel(
            name='MaterialPackagingUnit',
        ),
        migrations.DeleteModel(
            name='ProductPackagingUnit',
        ),
        migrations.DeleteModel(
            name='MaterialUnitChangeHistory',
        ),
        migrations.DeleteModel(
            name='ProductUnitChangeHistory',
        ),

        # ========== ItemUnitConversion 添加约束 ==========
        migrations.AddConstraint(
            model_name='itemunitconversion',
            constraint=models.UniqueConstraint(
                condition=models.Q(('content_type', 'material')),
                fields=['material', 'target_unit'],
                name='unique_material_target_unit',
            ),
        ),
        migrations.AddConstraint(
            model_name='itemunitconversion',
            constraint=models.UniqueConstraint(
                condition=models.Q(('content_type', 'product')),
                fields=['product', 'target_unit'],
                name='unique_product_target_unit',
            ),
        ),
    ]
