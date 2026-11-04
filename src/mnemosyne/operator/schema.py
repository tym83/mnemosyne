"""Structural CRD schemas; narrative documents deliberately retain unknown fields."""
DOCUMENT = {'type': 'object', 'x-kubernetes-preserve-unknown-fields': True}
STRING = {'type': 'string'}
RUNTIME = {'type': 'object', 'required': ['mode', 'inventory'], 'properties': {
    'mode': {'type': 'string', 'enum': ['chamber', 'background', 'GPU', 'API']},
    'render': {'type': 'boolean', 'default': True},
    'suspend': {'type': 'boolean', 'default': False},
    'deadlineSeconds': {'type': 'integer', 'minimum': 60, 'maximum': 604800},
    'drafts': {'type': 'integer', 'minimum': 1, 'maximum': 10},
    'snapshotNamespace': STRING,
    'includeSecrets': {'type': 'boolean', 'default': False},
    'climate': DOCUMENT, 'inner': STRING,
    'window': {'type': 'object', 'properties': {
        'kind': {'type': 'string', 'enum': ['night', 'weekends', 'idle', 'always']},
        'timeZone': STRING,
        'startHour': {'type': 'integer', 'minimum': 0, 'maximum': 23},
        'endHour': {'type': 'integer', 'minimum': 0, 'maximum': 23}}},
    'inventory': {'type': 'array', 'minItems': 1, 'items': {'type': 'object',
        'required': ['apiVersion', 'kind', 'resource'], 'properties': {
            'names': {'type': 'array', 'minItems': 1, 'items': STRING},
            'apiVersion': {'type': 'string', 'pattern': '^[a-z0-9.-]+(/[a-z0-9]+)?$'},
            'kind': {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9]*$'},
            'resource': {'type': 'string', 'pattern': '^[a-z][a-z0-9]*$'}}}},
    'commissions': {'type': 'array', 'items': {'type': 'object',
        'required': ['idea', 'method', 'plan'], 'properties': {
            'idea': {'type': 'string', 'minLength': 1},
            'method': {'type': 'string', 'minLength': 1}, 'plan': DOCUMENT}}},
}}


def schema(kind):
    fields = {'title': STRING, 'art': STRING}
    if kind == 'Atelier':
        fields['runtime'] = RUNTIME
    return {'type': 'object', 'properties': {
        'spec': {**DOCUMENT, 'properties': fields},
        'status': {**DOCUMENT, 'properties': {
            'phase': STRING, 'lastJob': STRING,
            'observedGeneration': {'type': 'integer', 'format': 'int64'},
            'conditions': {'type': 'array', 'x-kubernetes-list-type': 'map',
                'x-kubernetes-list-map-keys': ['type'], 'items': {
                    'type': 'object', 'required': ['type', 'status', 'reason', 'message', 'lastTransitionTime'],
                    'properties': {'type': STRING, 'status': {'type': 'string', 'enum': ['True', 'False', 'Unknown']},
                        'reason': STRING, 'message': STRING,
                        'lastTransitionTime': {'type': 'string', 'format': 'date-time'}}}}
        }}
    }}
