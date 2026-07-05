from django.conf import settings


def notification_badge(request):
    if not request.user.is_authenticated:
        return {'unread_notification_count': 0, 'vapid_public_key': settings.VAPID_PUBLIC_KEY}
    return {
        'unread_notification_count': request.user.notifications.filter(is_read=False).count(),
        'vapid_public_key': settings.VAPID_PUBLIC_KEY,
    }


def live_ticker(request):
    from .models import Match
    matches = list(
        Match.objects.select_related('home_player__user', 'away_player__user')
        .filter(status='played', home_score__isnull=False, away_score__isnull=False)
        .order_by('-played_at', '-created_at')[:10]
    )
    return {'ticker_matches': matches}
