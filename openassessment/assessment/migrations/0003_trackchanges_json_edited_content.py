# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0002_trackchanges'),
    ]

    operations = [
        migrations.AddField(
            model_name='trackchanges',
            name='json_edited_content',
            field=models.TextField(blank=True),
        ),
    ]
