import json
import types
from collections import OrderedDict
from functools import partial
from importlib import import_module

from django.contrib.admindocs.views import (
    named_group_matcher, non_named_group_matcher, simplify_regex
)
from django.core.exceptions import ValidationError
from django.forms.fields import MultiValueField, RegexField, TypedChoiceField
from django.utils.functional import cached_property, lazy
from django.utils.translation import ugettext_lazy as _
from django.urls import reverse, NoReverseMatch
from django.urls.resolvers import get_resolver, RegexURLPattern, RegexURLResolver

from .widgets import PlaceholderTextInput, URLResolverWidget


class URLPatternGroup(object):
    default_placeholder = 'var'

    def __init__(self, match):
        self.required = match.string[match.end()] != '?'
        self.regex = match.group()
        try:
            label = match.groups()[0]
        except IndexError:
            label = ''
        self.label = label

    @property
    def keyword(self):
        return self.label[1:-1] or None

    @property
    def placeholder(self):
        keyword = self.keyword or ''
        return keyword.replace('_', ' ') or self.default_placeholder

    def json_data(self):
        return {
            'required': self.required,
            'placeholder': self.placeholder
        }

    def field_data(self):
        return {
            'regex': self.regex,
            'label': self.label,
            'required': self.required,
            'placeholder': self.placeholder,
        }


class URLPattern(object):
    def __init__(self, urlpattern, name=None, pattern_obj=None):
        if name is None:
            name = pattern_obj.name
        self.name = name
        if pattern_obj is None:
            pattern_obj = urlpattern.regex.pattern
        self.pattern_obj = pattern_obj
        self._set_urlpattern(urlpattern)

    @cached_property
    def groups(self):
        def replace(groups, match):
            group = URLPatternGroup(match)
            group.start = match.start()
            groups.append(group)
            # Replace pattern so non-named group matcher does not find it again, but preserve the
            # string length so we can sort the group at the correct index later.
            return ' ' * len(match.group())
        result = []
        replace = partial(replace, result)

        p = named_group_matcher.sub(replace, self.pattern_obj.regex.pattern)
        p = non_named_group_matcher.sub(replace, p)

        result.sort(key=lambda g: g.start)
        return result

    def _get_urlpattern(self):
        return self._urlpattern

    def _set_urlpattern(self, urlpattern):
        self._urlpattern = urlpattern
        try:
            delattr(self, 'groups')
        except AttributeError:
            pass
    urlpattern = property(_get_urlpattern, _set_urlpattern)

    @property
    def simple_pattern(self):
        return simplify_regex(self.urlpattern)

    def group_json_data(self):
        json_data = [g.json_data() for g in self.groups]
        if json_data:
            return json.dumps(json_data)
        else:
            return ''


class URLPatterns(object):
    cache = {}

    def __new__(cls, urlconf):
        if urlconf in cls.cache:
            return cls.cache[urlconf]
        return super(URLPatterns, cls).__new__(cls)

    def __init__(self, urlconf):
        if self in self.cache.values():
            return
        self.urlconf = urlconf
        self.patterns = self.get_patterns()
        self.cache[urlconf] = self

    def __getitem__(self, key):
        if key in self.patterns:
            return self.patterns[key]
        raise KeyError(key)

    def __iter__(self):
        return iter(self.patterns)

    def items(self):
        return self.patterns.items()

    def _get_patterns(self):
        resolver = get_resolver(self.urlconf)
        return self.populate(resolver)
    get_patterns = lazy(_get_patterns, OrderedDict)

    def populate(self, resolver, base='', namespace=None):
        result = OrderedDict()
        for obj in resolver.url_patterns:
            pattern = obj.regex.pattern
            if base:
                pattern = base + pattern
            if isinstance(obj, RegexURLPattern):
                if not obj.name:
                    name = obj.lookup_str
                    pkg, viewname = name.rsplit('.', 1)
                    try:
                        module = import_module(pkg)
                        view = getattr(module, viewname)
                    except (ImportError, AttributeError):
                        continue
                    if not isinstance(view, types.FunctionType):
                        continue
                elif namespace:
                    name = '%s:%s' % (namespace, obj.name)
                else:
                    name = obj.name
                result[name] = URLPattern(pattern, name, obj)
            elif isinstance(obj, RegexURLResolver):
                if namespace and obj.namespace:
                    ns = '%s:%s' % (namespace, obj.namespace)
                else:
                    ns = obj.namespace or namespace
                result.update(self.populate(obj, pattern, ns))
        return result

    def as_choices(self):
        return [((k, v.group_json_data()), v.simple_pattern) for k, v in self.items()]


class URLPatternField(TypedChoiceField):
    def __init__(self, url_patterns, *args, **kwargs):
        self.url_patterns = url_patterns
        kwargs.update(coerce=lambda val: url_patterns[val[0]])
        super(URLPatternField, self).__init__(*args, **kwargs)

    def to_python(self, value):
        if value in self.empty_values:
            return ''
        return (value, self.url_patterns[value].group_json_data())


class URLRegexGroupField(RegexField):
    widget = PlaceholderTextInput
    default_error_messages = {
        'invalid': _('Enter a valid value for %(group)s.'),
    }

    def __init__(self, *args, **kwargs):
        label = kwargs.get('label', '')
        placeholder = kwargs.pop('placeholder', label[1:-1].replace('_', ' '))
        kwargs.update(widget=self.widget(placeholder=placeholder,
                                         attrs={'required': kwargs.get('required', False)}))
        super(URLRegexGroupField, self).__init__(*args, **kwargs)
        self.error_messages.update({
            'invalid': self.error_messages['invalid'] % {'group': label}
        })

    def widget_attrs(self, widget):
        return {'class': 'clone'}


class URLResolverField(MultiValueField):
    widget = URLResolverWidget
    default_error_messages = {
        'incomplete': _('Enter a complete value.'),  # TODO: Use more descriptive language
        'irreversible': _('Unable to find a valid URL.'),
    }

    def __init__(self, urlconf=None, *args, **kwargs):
        if urlconf is None:
            from django.conf import settings
            urlconf = settings.ROOT_URLCONF
        elif isinstance(urlconf, types.ModuleType):
            urlconf = urlconf.__name__

        # `require_all_fields` should never be true under any circumstances.
        kwargs.update(require_all_fields=False)
        required = kwargs.get('required', True)
        url_patterns = URLPatterns(urlconf)

        # Choices need to be retrieved from a callable otherwise a race condition could be created
        # on app initialization when iterating over urlconf's patterns.
        def choices():
            # TODO: Split into optgroups for apps
            choices = []
            if not required:
                choices.append(('', "---------"))
            return choices + url_patterns.as_choices()

        fields = [URLPatternField(url_patterns, choices, required=required)]
        widget = self.widget(url_patterns)
        kwargs.update(widget=widget)
        super(URLResolverField, self).__init__(fields, *args, **kwargs)

        self.widget.widgets[0].choices = self.fields[0].choices
        self.url_patterns = url_patterns

    def clean(self, value):
        # `value` is a list comprising each fields' values.  If the list
        # contains more than one value, we will need to create additional
        # fields that were not present at initializtion.
        if len(value) > 1:
            self.fields = list(self.fields)
            name = value[0]
            groups = self.url_patterns[name].groups
            for i, v in enumerate(value[1:]):
                field = URLRegexGroupField(**groups[i].field_data())
                field.error_messages.setdefault('incomplete',
                                                self.error_messages['incomplete'])
                self.fields.append(field)
        return super(URLResolverField, self).clean(value)

    def compress(self, data_list):
        if not data_list:
            return ''
        urlpattern = data_list.pop(0)
        urlconf = self.url_patterns.urlconf
        args = []
        kwargs = {}
        for i, g in enumerate(urlpattern.groups):
            if g.keyword:
                kwargs.update({g.keyword: data_list[i]})
            else:
                args.append(data_list[i])
        try:
            result = reverse(urlpattern.name, urlconf=urlconf, args=args, kwargs=kwargs)
        except ValueError as e:
            # `reverse` called with both args and kwargs. Raise the error, as
            # this is a configuration problem that we shouldn't hide.
            raise e
        except NoReverseMatch:
            # Try to reverse with view callback function.
            try:
                result = reverse(urlpattern.pattern_obj.callback, urlconf=urlconf,
                                 args=args, kwargs=kwargs)
            except NoReverseMatch:
                raise ValidationError(self.error_messages['irreversible'], code='irreversible')
        return result
