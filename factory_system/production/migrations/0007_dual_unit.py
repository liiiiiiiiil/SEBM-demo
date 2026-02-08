# 双单位系统迁移 - production 应用
# 移除已不再需要的 unit CharField 字段

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('production', '0006_add_material_requisition_item_batch'),
        ('inventory', '0022_dual_unit_phase2'),  # 确保 inventory 迁移完成
    ]

    operations = [
        # 移除 MaterialRequisitionItem.unit（数量已统一为基础单位）
        migrations.RemoveField(
            model_name='materialrequisitionitem',
            name='unit',
        ),
        # 移除 FinishedProductInbound.unit（数量已统一为基础单位）
        migrations.RemoveField(
            model_name='finishedproductinbound',
            name='unit',
        ),
    ]
