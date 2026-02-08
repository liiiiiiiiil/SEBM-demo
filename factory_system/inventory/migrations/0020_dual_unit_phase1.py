# 双单位系统迁移 - 阶段1：添加新字段（保留旧字段）
# 此迁移添加所有新的字段和模型，但保持旧字段不动，确保数据安全

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0019_remove_bom_unit'),
    ]

    operations = [
        # ========== Unit 模型修改 ==========
        # 添加 symbol 字段
        migrations.AddField(
            model_name='unit',
            name='symbol',
            field=models.CharField(blank=True, default='', max_length=10, verbose_name='单位符号'),
        ),
        # 移除 is_base 字段
        migrations.RemoveField(
            model_name='unit',
            name='is_base',
        ),
        # 修改 category 选项（去掉 packaging，加上 area）
        migrations.AlterField(
            model_name='unit',
            name='category',
            field=models.CharField(
                choices=[
                    ('weight', '重量'),
                    ('length', '长度'),
                    ('volume', '体积'),
                    ('quantity', '数量'),
                    ('area', '面积'),
                ],
                max_length=20,
                verbose_name='单位类别',
            ),
        ),

        # ========== Material 模型修改 ==========
        # 添加 display_unit（先 nullable，数据迁移后再设为 NOT NULL）
        migrations.AddField(
            model_name='material',
            name='display_unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='display_unit_materials',
                to='inventory.unit',
                verbose_name='显示单位',
            ),
        ),
        # 修改 base_unit 的 related_name
        migrations.AlterField(
            model_name='material',
            name='base_unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='base_unit_materials',
                to='inventory.unit',
                verbose_name='基础单位',
            ),
        ),

        # ========== Product 模型修改 ==========
        # 添加 display_unit
        migrations.AddField(
            model_name='product',
            name='display_unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='display_unit_products',
                to='inventory.unit',
                verbose_name='显示单位',
            ),
        ),
        # 修改 base_unit 的 related_name
        migrations.AlterField(
            model_name='product',
            name='base_unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='base_unit_products',
                to='inventory.unit',
                verbose_name='基础单位',
            ),
        ),

        # ========== BOM 模型修改 ==========
        # 添加 unit FK（先 nullable）
        migrations.AddField(
            model_name='bom',
            name='unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='bom_items',
                to='inventory.unit',
                verbose_name='用量单位',
            ),
        ),
        # 修改 quantity 精度为 10,4
        migrations.AlterField(
            model_name='bom',
            name='quantity',
            field=models.DecimalField(
                decimal_places=4,
                max_digits=10,
                verbose_name='用量',
            ),
        ),

        # ========== StockTransaction 模型修改 ==========
        # 重命名 unit -> unit_legacy
        migrations.RenameField(
            model_name='stocktransaction',
            old_name='unit',
            new_name='unit_legacy',
        ),
        # 添加新的 unit FK（nullable）
        migrations.AddField(
            model_name='stocktransaction',
            name='unit',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='stock_transactions',
                to='inventory.unit',
                verbose_name='操作单位',
            ),
        ),
        # 添加 base_quantity
        migrations.AddField(
            model_name='stocktransaction',
            name='base_quantity',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='基础单位数量',
            ),
        ),

        # ========== InventoryAdjustmentRequest 模型修改 ==========
        # 修改 adjustment_type 选项（移除 unit）
        migrations.AlterField(
            model_name='inventoryadjustmentrequest',
            name='adjustment_type',
            field=models.CharField(
                choices=[
                    ('quantity', '数量调整'),
                    ('price', '单价调整'),
                    ('both', '数量+单价调整'),
                ],
                default='quantity',
                max_length=20,
                verbose_name='调整类型',
            ),
        ),

        # ========== 创建 ItemUnitConversion 模型 ==========
        migrations.CreateModel(
            name='ItemUnitConversion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content_type', models.CharField(
                    choices=[('material', '原料'), ('product', '成品')],
                    max_length=20,
                    verbose_name='关联类型',
                )),
                ('factor', models.DecimalField(
                    decimal_places=6,
                    max_digits=15,
                    validators=[django.core.validators.MinValueValidator(0.000001)],
                    verbose_name='换算系数（1目标单位=N基础单位）',
                )),
                ('is_default', models.BooleanField(default=False, verbose_name='是否默认展示单位')),
                ('is_active', models.BooleanField(default=True, verbose_name='是否启用')),
                ('remark', models.TextField(blank=True, verbose_name='备注')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='创建时间')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='更新时间')),
                ('base_unit', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='conversion_base',
                    to='inventory.unit',
                    verbose_name='基础单位',
                )),
                ('target_unit', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='conversion_target',
                    to='inventory.unit',
                    verbose_name='目标单位',
                )),
                ('material', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='unit_conversions',
                    to='inventory.material',
                    verbose_name='原料',
                )),
                ('product', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='unit_conversions',
                    to='inventory.product',
                    verbose_name='成品',
                )),
            ],
            options={
                'verbose_name': '物品单位换算',
                'verbose_name_plural': '物品单位换算',
                'db_table': 'inventory_item_unit_conversion',
                'ordering': ['content_type', 'material', 'product', 'target_unit'],
            },
        ),
    ]
