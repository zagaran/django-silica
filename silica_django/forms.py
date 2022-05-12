from collections import defaultdict

from django import forms

from silica_django.fields import SilicaSubFormArrayField
from silica_django.layout import Control, VerticalLayout, CustomElement
from silica_django.mixins import JsonSchemaMixin


class SilicaFormMixin(JsonSchemaMixin, forms.Form):
    """ Adds Silica functionality to any Django form.

        Required Meta fields:
        @fields - a list of fields you wish to be rendered. These should correspond to the form's @fields attribute.

        Optional Meta fields:
        @rules - a mapping of fields to the rules which should be applied to controls.
        @layout - a custom SilicaLayout. This will be used instead of generating a layout from your fields. 
                         Note that rules will still be applied.
        @custom_ui_schema - a mapping of fields to a dictionary matching the UISchema pattern.
        @custom_components - a mapping of fields to the name of the custom Control renderer you want to use.

     """
    class Meta:
        silica_config = None
        layout = None

    def __init__(self, *args, **kwargs):
        # if we are intaking data from a POST, process it
        new_args = [*args]
        if len(args) > 0:
            # we have to mutate the querydict, so make a copy
            raw_data = new_args[0].copy()
            array_info = self._extract_array_info(raw_data)
            for key, values in array_info.items():
                raw_data[key] = values
            new_args = [raw_data, *args]
        self.instance = kwargs.get('instance')
        super().__init__(*new_args, **kwargs)
        self._setup_array_fields()

    def get_silica_config(self):
        if hasattr(self.Meta, 'silica_config'):
            return self.Meta.silica_config
        return None

    def get_field_config(self, field_name):
        silica_config = self.get_silica_config()
        if silica_config:
            return self.Meta.silica_config.get_field_config(field_name)
        return None
    
    def _setup_array_fields(self):
        for field in self.fields.values():
            if isinstance(field, SilicaSubFormArrayField):
                field.parent_instance = self.instance

    def _extract_array_info(self, raw_data):
        # iterate over raw data keys; if any are an array field, then process it
        array_items_by_name_and_count = defaultdict(lambda: defaultdict(dict))
        for key, value in raw_data.items():
            # array fields are named using the following pattern:
            # <array_form_field>.<item_count>.<form_field>
            split_key = key.split('.') # extract pieces
            if len(split_key) < 3:
                # not an array field
                continue
            array_field_name = split_key[0]
            count = split_key[1]
            field = split_key[2]
            array_items_by_name_and_count[array_field_name][count][field] = value
        # each array field should have its own list of objects
        array_field_data = {
            array_field_name: values_by_count.values()
            for array_field_name, values_by_count in array_items_by_name_and_count.items()
        }
        return array_field_data

    def get_errors_for_template(self):
        return {
            field_name: [e for e in errors] for field_name, errors in self.errors.items()
        }

    def get_data_for_template(self):
        initial = {}
        for field_name, field in self.fields.items():
            if isinstance(field, SilicaSubFormArrayField):
                field.refresh_data()
            # first check instance
            if self.instance and hasattr(self.instance, field_name) and not isinstance(field,
                                                                                       SilicaSubFormArrayField):
                initial[field_name] = getattr(self.instance, field_name)
            elif field_name in self.initial:
                initial[field_name] = self.initial[field_name]
            else:
                initial[field_name] = field.initial
            # if a model is new, use the initial value of the field (if it exists) to override
            if self.instance._state.adding and field.initial:
                initial[field_name] = field.initial
        return initial

    def get_ui_schema(self):
        # this function is only ever called after the form has been instantiated, so we have access to self.fields
        if hasattr(self.Meta, 'layout'):
            return self.Meta.layout.get_ui_schema(self)
        elements = []
        for field_name, field in self.fields.items():
            ui_kwargs = self._django_widget_to_ui_schema(field, field_config=self.get_field_config(field_name))
            element = Control(field_name, **ui_kwargs)
            elements.append(element)
        return VerticalLayout(*elements).get_ui_schema(self)

    def get_data_schema(self):
        """ Schema is used by the frontend to validate rules """
        # TODO: refine this to support more complex jsonschema rules and to (perhaps) simplify redundant rules
        # TODO: support error_message https://stackoverflow.com/questions/65303161/how-can-i-override-default-error-messages-text-in-json-forms
        properties = {
            field_name: self._django_to_jsonschema_field(field_name, field, field_config=self.get_field_config(field_name))
            for field_name, field in self.fields.items()
        }
        return {
            "type": "object",
            "properties": properties
        }
    
    @property
    def custom_elements(self):
        """ Returns a list of CustomElement items in the form's Meta.layout """
        if hasattr(self.Meta, 'layout'):
            return list(filter(lambda e: isinstance(e, CustomElement), self.Meta.layout))
        return []

    def get_custom_elements_content(self):
        custom_elements_content = {}
        for element in self.custom_elements:
            custom_elements_content.update(element.get_mapped_content)
        return custom_elements_content


class SilicaModelFormMixin(SilicaFormMixin, forms.ModelForm):
    def save(self, commit=True):
        # save array fields before continuing with save
        for field in self.fields.values():
            if isinstance(field, SilicaSubFormArrayField):
                field.do_save()
        return super().save(commit=commit)
