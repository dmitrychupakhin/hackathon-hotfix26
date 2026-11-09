from django.db import connection


def register_file(attachment, owner_id):
    with connection.cursor() as cursor:
        cursor.execute(
            '''INSERT INTO ai.files
               (owner, id, version, filename, relative_path, sha256, media_type)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (owner, id) DO UPDATE SET
                 version = EXCLUDED.version,
                 filename = EXCLUDED.filename,
                 relative_path = EXCLUDED.relative_path,
                 sha256 = EXCLUDED.sha256,
                 media_type = EXCLUDED.media_type,
                 updated_at = now()''',
            [str(owner_id), str(attachment.id), attachment.sha256,
             attachment.original_name, attachment.file.name, attachment.sha256,
             attachment.media_type],
        )


def unregister_files(owner_id, file_ids):
    if not file_ids:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            'DELETE FROM ai.files WHERE owner = %s AND id = ANY(%s)',
            [str(owner_id), [str(file_id) for file_id in file_ids]],
        )
