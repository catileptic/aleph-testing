from banal import ensure_list
from flask import Blueprint, request, send_file

from aleph.search import XrefQuery
from aleph.logic.xref import export_matches
from aleph.views.serializers import MatchSerializer
from aleph.queues import queue_task, OP_XREF
from aleph.views.util import get_db_collection, get_index_collection, jsonify
from aleph.views.util import parse_request

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'  # noqa
blueprint = Blueprint('xref_api', __name__)


@blueprint.route('/api/2/collections/<int:collection_id>/xref', methods=['GET'])  # noqa
def index(collection_id):
    """
    ---
    get:
      summary: Fetch cross-reference summary
      description: >-
        Fetch cross-reference matches grouped by collection, for entities in
        the collection with id `collection_id`
      parameters:
      - in: path
        name: collection_id
        required: true
        schema:
          type: integer
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                type: object
                allOf:
                - $ref: '#/components/schemas/QueryResponse'
                properties:
                  results:
                    type: array
                    items:
                      $ref: '#/components/schemas/XrefCollection'
      tags:
      - Xref
      - Collection
    """
    get_index_collection(collection_id)
    result = XrefQuery.handle(request, collection_id=collection_id)
    return MatchSerializer.jsonify_result(result)


@blueprint.route('/api/2/collections/<int:collection_id>/xref', methods=['POST'])  # noqa
def generate(collection_id):
    """
    ---
    post:
      summary: Generate cross-reference matches
      description: >
        Generate cross-reference matches for entities in a collection.
      parameters:
      - in: path
        name: collection_id
        required: true
        schema:
          type: integer
      requestBody:
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/XrefGenerate'
      responses:
        '202':
          content:
            application/json:
              schema:
                properties:
                  status:
                    description: accepted
                    type: string
                type: object
          description: Accepted
      tags:
      - Xref
      - Collection
    """
    data = parse_request('XrefGenerate')
    collection = get_db_collection(collection_id, request.authz.WRITE)
    against = ensure_list(data.get("against_collection_ids"))
    payload = {'against_collection_ids': against}
    queue_task(collection, OP_XREF, payload=payload)
    return jsonify({'status': 'accepted'}, status=202)


@blueprint.route('/api/2/collections/<int:collection_id>/xref/export')
def export(collection_id):
    """
    ---
    get:
      summary: Download cross-reference results
      description: Download results of cross-referencing as an Excel file
      parameters:
      - in: path
        name: collection_id
        required: true
        schema:
          type: integer
      responses:
        '200':
          description: OK
          content:
            application/vnd.openxmlformats-officedocument.spreadsheetml.sheet:
              schema:
                type: object
      tags:
      - Xref
      - Collection
    """
    collection = get_index_collection(collection_id, request.authz.READ)
    buffer = export_matches(collection_id, request.authz)
    file_name = '%s - Crossreference.xlsx' % collection.get('label')
    return send_file(buffer,
                     mimetype=XLSX_MIME,
                     as_attachment=True,
                     attachment_filename=file_name)
