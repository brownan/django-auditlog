
from django.db.models.fields.related import RelatedField


class LogRelationsRegistry(dict):

    def register(self, model, relations):
        self._validate_relations(model, relations)
        self[model] = relations

    def unregister(self, model):
        self.pop(model, None)

    def _validate_relations(self, model, relations):
        """
        Validate that the relation strings represent actual relations
        """
        for relation in relations:
            parent = model

            for part in relation.split('__'):
                # Additionally, we could try looking up child relationships
                # Related FK and m2m relations can be accessed by name via
                # _meta.get_field_by_name
                field = parent._meta.get_field(part)
                if isinstance(field, RelatedField):
                    parent = field.related.parent_model
                else:
                    raise ValueError("Error on '%s': '%s' has no relation '%s'" % (model, parent, part))

logrels = LogRelationsRegistry()
auditrels = logrels
