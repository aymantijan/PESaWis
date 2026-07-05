import json
import logging

from django.conf import settings
from pywebpush import WebPushException, webpush

logger = logging.getLogger(__name__)


def send_web_push(user, title, message, link=''):
    """Push a browser/phone notification to every device the user subscribed from."""
    if not getattr(settings, 'VAPID_PRIVATE_KEY', ''):
        return
    subscriptions = user.push_subscriptions.all()
    if not subscriptions:
        return
    payload = json.dumps({
        'title': title,
        'body': message,
        'url': link or '/notifications/',
        'icon': settings.STATIC_URL + 'images/pesawis-logo.png',
    })
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': f'mailto:{settings.VAPID_CLAIM_EMAIL}'},
            )
        except WebPushException as exc:
            logger.warning('Push failed for %s: %s', user.username, exc)
            if exc.response is not None and exc.response.status_code in (404, 410):
                subscription.delete()
