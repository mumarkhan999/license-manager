# Generated by Django 2.2.19 on 2021-03-24 19:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0020_help_text_for_default_catalog_uuid'),
    ]

    operations = [
        migrations.AddField(
            model_name='subscriptionsroleassignment',
            name='applies_to_all_contexts',
            field=models.BooleanField(default=False, help_text='If true, indicates that the user is effectively assigned their role for any and all contexts. Defaults to False.'),
        ),
    ]
