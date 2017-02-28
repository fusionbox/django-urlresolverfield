from django.forms.widgets import MultiWidget, Select, TextInput
from django.template import Context
from django.template.loader import get_template
from django.urls import resolve, Resolver404
from django.utils.encoding import force_text
from django.utils.html import format_html
from django.utils.safestring import mark_safe


class URLPatternSelect(Select):
    """A Select Widget meant to handle url patterns

    It renders json data about its pattern's regex capture groups inside a data attribute.

    Its JavaScript media uses this data to create clones of a widget template used to accept values
    for the capture groups.
    """
    class Media:
        js = ('urlresolverfield/js/widget.js',)

    def render_option(self, selected_choices, option_value, option_label):
        if option_value is None:
            option_value = ''
        if option_value:
            option_value, option_data = option_value
            if option_data:
                option_data_html = mark_safe(" data-groups='{}'".format(option_data))
            else:
                option_data_html = ''
        else:
            option_data_html = ''
        option_value = force_text(option_value)
        if option_value in selected_choices:
            selected_html = mark_safe(' selected="selected"')
            selected_choices.remove(option_value)
        else:
            selected_html = ''
        return format_html('<option value="{}"{}{}>{}</option>',
                           option_value, selected_html, option_data_html, force_text(option_label))


class PlaceholderTextInput(TextInput):
    "A TextInput Widget that accepts an optional placeholder attribute"
    def __init__(self, placeholder=None, attrs=None):
        super(PlaceholderTextInput, self).__init__(attrs)
        if placeholder:
            self.attrs.update(placeholder=placeholder)


class URLResolverWidget(MultiWidget):
    select_widget_class = URLPatternSelect
    text_input_widget_class = PlaceholderTextInput

    def __init__(self, url_patterns, attrs=None):
        self.url_patterns = url_patterns
        widgets = [self.select_widget_class()]
        super(URLResolverWidget, self).__init__(widgets, attrs)

    def render(self, name, value, attrs=None):
        # Overridden for a handful of reasons:
        # - Additional widgets must be added if the value requires them and the do not yet exist.
        # - Attributes sent to widgets differ depending on whether the widget is the select or the
        #   text input.
        # - A template text input widget must be rendered using this widget's field name.
        if self.is_localized:
            for widget in self.widgets:
                widget.is_localized = self.is_localized
        if not isinstance(value, list):
            value = self.decompress(value)
        if len(self.widgets) != len(value):
            self.init_widgets(value[0])
        if attrs is None:
            attrs = {}
        try:
            css_classes = attrs.get('class').split(' ')
        except AttributeError:
            css_classes = []
        template_id = 'template_%s' % name
        output = []
        for i, widget in enumerate(self.widgets):
            try:
                widget_value = value[i]
            except IndexError:
                widget_value = None
            attrs_ = attrs.copy() or {}
            if isinstance(widget, self.select_widget_class):
                attrs_['data-template-id'] = template_id
                css_classes_ = css_classes + ['urlresolver']
            else:
                attrs_.update(required=widget.attrs.get('required', False))
                css_classes_ = css_classes + ['clone']
            attrs_.update({'class': ' '.join(css_classes_).strip()})
            final_attrs = self.build_attrs(attrs_)
            id_ = final_attrs.get('id')
            if id_:
                final_attrs = dict(final_attrs, id='%s_%s' % (id_, i))
            output.append(widget.render(name + '_%s' % i, widget_value, final_attrs))

        class URLRegexGroupInputClone(self.text_input_widget_class):
            """One-time-usage Widget to produce an unrendered HTML template

            JavaScript from URLResolverWidget's `select_widget_class` duplicates this HTML and
            populates clones with real values.
            """
            def render(self, name, value, *args, **kwargs):
                name += '_{{index}}'
                template = get_template('urlresolverfield/widget_clone.html')
                output = super(URLRegexGroupInputClone, self).render(name, value, *args, **kwargs)
                return template.render(Context({'template_id': template_id, 'widget': output}))

        template_html = URLRegexGroupInputClone(placeholder='{{placeholder}}').render(name, None)
        return mark_safe(self.format_output(output + [template_html]))

    def decompress(self, value):
        "Turns a path string into a list of view name (or function path), args and kwargs"
        try:
            match = resolve(value, urlconf=self.url_patterns.urlconf)
        except Resolver404:
            return [None]
        match_args = list(match.args)
        try:
            groups = self.url_patterns[match.view_name].groups
            result = [match.view_name]
        except KeyError:
            groups = self.url_patterns[match._func_path].groups
            result = [match._func_path]
        for g in groups:
            if g.keyword:
                result.append(match.kwargs[g.keyword])
            else:
                result.append(match_args.pop(0))
        return result

    def value_from_datadict(self, data, files, name):
        pattern_value = data.get('%s_0' % name)
        if pattern_value and len(self.widgets) < 2:
            # A widget does not exist for each of the field's values in the submitted form. This is
            # because the field widgets were added dynamically by JavaScript and no corresponding
            # fields existed when the field was created.
            self.init_widgets(pattern_value)
        return super(URLResolverWidget, self).value_from_datadict(data, files, name)

    def init_widgets(self, pattern_value):
        "Initializes a widget for each regex capture group used by the url pattern"
        groups = self.url_patterns[pattern_value].groups
        for g in groups:
            self.widgets.append(
                self.text_input_widget_class(placeholder=g.placeholder,
                                             attrs={'required': g.required})
            )
