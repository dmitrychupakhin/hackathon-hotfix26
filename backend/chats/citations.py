"""Public citation links are derived from trusted owner-scoped uploaded files.

Never use a model-provided URL/path, and never infer identity from filenames.
Offsets are Unicode code points with an exclusive end, not UTF-16 indexes.
"""
import re
from urllib.parse import urlencode


HASH = re.compile(r'^[a-f0-9]{64}$')


def build_citations(answer, chat):
    files = {str(item.id): item for item in chat.files.all()}
    result = []
    seen = set()
    for span in answer.get('evidence') or []:
        if not isinstance(span, dict):
            continue
        attachment = files.get(span.get('source_file_id'))
        start, end = span.get('start'), span.get('end')
        quote, digest = span.get('text'), span.get('source_hash')
        if (attachment is None or span.get('original_sha256') != attachment.sha256
                or span.get('source_version') != attachment.sha256
                or not isinstance(digest, str) or HASH.fullmatch(digest) is None
                or type(start) is not int or type(end) is not int or start < 0 or end <= start
                or not isinstance(quote, str) or len(quote) != end - start):
            continue
        key = (str(attachment.id), digest, start, end)
        if key in seen:
            continue
        seen.add(key)
        query = urlencode({'text_sha256': digest, 'version': span['source_version']})
        result.append({
            'id': f'{attachment.id}:{digest}:{start}:{end}',
            'file_id': str(attachment.id), 'file_name': attachment.original_name,
            'quote': quote, 'start': start, 'end': end, 'text_sha256': digest,
            'version': span['source_version'], 'locations': span.get('locations') or [],
            'preview_url': f'/api/chats/{chat.id}/files/{attachment.id}/preview?{query}',
            'offset_unit': 'unicode_code_points',
            'anchor_method': span.get('anchor_method', 'harness_evidence'),
        })
    return result
