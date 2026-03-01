# Generated manually for per-item manual_batch_allocation

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0014_salesorder_manual_batch_allocation'),
    ]

    operations = [
        migrations.AddField(
            model_name='salesorderitem',
            name='manual_batch_allocation',
            field=models.BooleanField(default=False, verbose_name='手动分配批次'),
        ),
    ]
