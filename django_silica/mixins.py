from django import forms

from django_silica import fields
from django_silica.utils.jsonschema import JsonSchemaUtils


class JsonSchemaMixin(JsonSchemaUtils):
    """ Contains utility functions for interfacing between native python/django and jsonschema """
    def django_to_jsonschema_field(self, field_name, field):
        # most field types are string by default
        field_type = "string"
        # format is only required for some special types e.g. date
        field_kwargs = {
            'name': field_name,
            'options': {}
        }
        if isinstance(field, forms.DateField):
            field_kwargs["format"] = "date"
        elif isinstance(field, forms.DateTimeField):
            field_kwargs["format"] = "date-time"
        elif isinstance(field, forms.TimeField):
            field_kwargs["format"] = "time"
        elif isinstance(field, forms.IntegerField):
            field_type = "integer"
        elif isinstance(field, forms.FloatField) or isinstance(field, forms.DecimalField):
            field_type = "number"
        elif isinstance(field, forms.BooleanField):
            field_type = "boolean"
        # todo: differentiate between arrays of related items and a multi field (e.g. tags)
        elif isinstance(field, fields.SilicaFormArrayField):
            field_type = "array"
            if field.instantiated_forms:
                item_schema = field.instantiated_forms[0].get_schema()
            else:
                # there are no existing sub-items, instantiate the form to get the schema
                item_schema = field.instance_form().get_schema()
            item_schema["properties"][field.identifier_field] = {
                    "type": "number",
                    "hidden": True
                }
            field_kwargs['items'] = {
                **item_schema,
            }            
        if hasattr(field, 'choices'):
            field_kwargs["oneOf"] = [{'const': value, 'title': title} for (value, title) in field.choices]
        if hasattr(self.Meta, 'custom_components') and field_name in self.Meta.custom_components:
            field_kwargs['customComponentName'] = self.Meta.custom_components[field_name]
        # special checks
        if isinstance(field.widget, forms.HiddenInput):
            field_kwargs['hidden'] = True
        if field.disabled:
            field_kwargs['readOnly'] = True
        if isinstance(field.widget, forms.RadioSelect):
            field_kwargs['options']['format'] = "radio"
            # for a radio select, everything is a string - we'll convert on the backend
            field_type = "string"
            if not hasattr(field, 'choices'):
                field_kwargs["oneOf"] = [{'const': value, 'title': title} for (value, title) in field.widget.choices]
        return {
            "type": field_type,
            **field_kwargs
        }