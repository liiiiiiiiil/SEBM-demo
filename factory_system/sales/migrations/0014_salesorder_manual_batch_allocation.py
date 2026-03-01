# Generated manually for manual_batch_allocation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0013_convert_order_quantities_to_base_unit'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorder',
            name='manual_batch_allocation',
            field=models.BooleanField(default=False, verbose_name='手动分配批次'),
        ),
    ]
