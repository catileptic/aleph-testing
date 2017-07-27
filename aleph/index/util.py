import six
import logging
import fingerprints
from elasticsearch.helpers import bulk
from normality import stringify, latinize_text, collapse_spaces, ascii_text

from aleph.core import es, es_index
from aleph.util import is_list, unique_list, remove_nulls

log = logging.getLogger(__name__)
INDEX_MAX_LEN = 1024 * 1024 * 100


def unpack_result(res):
    if 'found' in res and not res.get('found'):
        return
    data = res.get('_source')
    data['id'] = res.get('_id')
    data['$type'] = res.get('_type')
    if '_score' in res:
        data['$score'] = res.get('_score')
    return data


def bulk_op(iter, chunk_size=500):
    bulk(es, iter, stats_only=True, chunk_size=chunk_size,
         request_timeout=200.0)


def query_delete(query, doc_type=None, wait=True):
    "Delete all documents matching the given query inside the doc_type(s)."
    if doc_type is None:
        doc_type = '*'
    es.delete_by_query(index=six.text_type(es_index),
                       body={'query': query},
                       doc_type=doc_type,
                       refresh=True,
                       conflicts='proceed',
                       wait_for_completion=wait)


def merge_docs(old, new):
    """Exend the values of the new doc with extra values from the old."""
    old = remove_nulls(old)
    new = dict(remove_nulls(new))
    for k, v in old.items():
        if k == 'created_at':
            new[k] = v
        elif k in new:
            if is_list(v):
                v = new[k] + v
                new[k] = unique_list(v)
            elif isinstance(v, dict):
                new[k] = merge_docs(v, new[k])
        else:
            new[k] = v
    return new


def index_form(texts):
    """Turn a set of strings into the appropriate form for indexing."""
    results = []
    total_len = 0

    for text in texts:
        # We don't want to store more than INDEX_MAX_LEN of text per doc
        if total_len > INDEX_MAX_LEN:
            # TODO: there might be nicer techniques for dealing with overly
            # long text buffers?
            results = list(set(results))
            total_len = sum((len(t) for t in results))
            if total_len > INDEX_MAX_LEN:
                break

        text = stringify(text)
        if text is None:
            continue
        text = collapse_spaces(text)
        total_len += len(text)
        results.append(text)

        # Make latinized text version
        latin = latinize_text(text)
        latin = stringify(latin)
        if latin is None or latin == text:
            continue
        total_len += len(latin)
        results.append(latin)
    return results


def index_names(data):
    """Handle entity names on documents and entities."""
    names = data.get('names', [])
    fps = [fingerprints.generate(name) for name in names]
    fps = [fp for fp in fps if fp is not None]
    data['fingerprints'] = list(set(fps))

    # Add latinised names
    for name in list(names):
        names.append(ascii_text(name))
    data['names'] = list(set(names))
