from django.db import migrations


def create_default_categories(apps, schema_editor):
    Category = apps.get_model("inventory", "Category")
    for name in ("成品", "原料"):
        Category.objects.get_or_create(name=name)


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_default_categories, migrations.RunPython.noop),
    ]

