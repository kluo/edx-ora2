# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TrackChanges',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('owner_submission_uuid', django_extensions.db.fields.UUIDField(db_index=True, version=1, editable=False, blank=True)),
                ('scorer_id', models.CharField(max_length=40, db_index=True)),
                ('edited_content', models.TextField(blank=True)),
            ],
        ),
    ]
