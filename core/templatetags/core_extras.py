from django import template

register = template.Library()

@register.filter
def yesno_icon(value):
    return '✓' if value else '—'


@register.filter
def notification_icon(notification_type):
    mapping = {
        'friendly_request': '⚔️',
        'match_update': '📅',
        'comment': '💬',
        'tag': '🏷️',
        'tournament_invite': '🏆',
        'system': '🔔',
    }
    return mapping.get(notification_type, '🔔')


@register.filter
def outcome_class(value):
    mapping = {
        'Champion': 'outcome-promoted',
        'Promoted': 'outcome-promoted',
        'Relegated': 'outcome-relegated',
        'Relegation zone': 'outcome-relegated',
        'Safe': 'outcome-stays',
    }
    return mapping.get(value, 'outcome-stays')
