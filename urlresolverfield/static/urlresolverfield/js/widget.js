(function() {
    // TODO: Test for template tag compatability and fall back to an html
    // templating JS lib if necessary.
    // eg. `if ('content' in document.createElement('template')) ...`

    var selects = document.getElementsByClassName('urlresolver');

    function onchange (el, i) {
        var template = document.getElementById(el.dataset['templateId']);

        el.onchange = function(event) {
            var select = event.target,
                value = select.value,
                groupData = select.options[select.selectedIndex].dataset['groups'],
                groups = [];

            if (groupData) {
                groups = JSON.parse(groupData);
            }

            el.parentNode.querySelectorAll('.clone').forEach(function(el) {
                el.parentNode.removeChild(el);
            });

            groups.forEach(function(group, i) {
                var clone = document.importNode(template.content, true);

                clone.childNodes[0].className += ' clone';
                group.index = i + 1;

                (function (el) {
                    el.name = el.name.replace(/{{index}}/g, group.index);
                    el.setAttribute('placeholder', el.getAttribute('placeholder').replace(/{{placeholder}}/g, group.placeholder));
                    if (group.required) {
                        el.setAttribute('required', '');
                    }
                })(clone.querySelector('input'));

                el.parentNode.appendChild(clone);
            });
        }
    }
    Array.prototype.forEach.call(selects, onchange);
})();
