from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processes', '0261_merge_python312_django52'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskfield',
            name='template_default',
            field=models.TextField(blank=True, default=''),
        ),
    ]
