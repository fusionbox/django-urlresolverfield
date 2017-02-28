Django URL Resolver Field
=========================

What is it?
-----------

A form field that takes a URL conf and provides the inputs necessary for a user to submit any valid
path (even variable paths!).

How does it work?
-----------------

By creating a MultiValueField and associated MultiWidget which combine a ChoiceField and any number
of RegexFields needed to fill the URL pattern's capture groups.

The field's widget renders a hidden template widget alongside its select tag that gets cloned
whenever an option is selected for a url pattern with capture groups. These clones are submitted
along with the form and used to reverse a valid path.

As of now, the template widget is created and manipulated as an html <template>. It might be useful
to include an option of using a number of popular JS html templating libraries in the future.

Is this a hack?
---------------

Sure is! I'm pretty sure this a very atypical use of Django fields & widgets. That said, it works.
