# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


def populate_json_edited_content(apps, schema_editor):
    # Populate json_edited_content with a json version of edited_content
    # that allows multiple prompts per question.
    TrackChanges = apps.get_model('assessment', 'TrackChanges')
    track_changes = TrackChanges.objects.all()
    for track_change in track_changes:
        part = []
        parts = {}
        edited_content_json = {}

        edited_content = track_change.edited_content

        edited_content_json['text'] = edited_content
        part.append(edited_content_json)
        parts['parts'] = part

        track_change.json_edited_content = json.dumps(parts)
        track_change.save()


class Migration(migrations.Migration):

    dependencies = [
        ('assessment', '0003_trackchanges_json_edited_content'),
    ]

    operations = [
        migrations.RunPython(populate_json_edited_content),
    ]
