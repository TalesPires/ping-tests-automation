# Generated by Django 4.2.20 on 2025-03-28 15:06

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pingtest', '0002_networktestresult_sw_name'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='networktestresult',
            options={},
        ),
        migrations.RemoveField(
            model_name='networktestresult',
            name='created_at',
        ),
    ]
