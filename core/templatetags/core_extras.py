from django import template

register = template.Library()

@register.filter
def yesno_icon(value):
    return '✓' if value else '—'
