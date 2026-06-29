from django.apps import apps
from django.contrib.auth.models import User
from django.db import IntegrityError, OperationalError, ProgrammingError
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import NotificationPreference, PlayerProfile


def default_konami_id(user):
    return f"AUTO-{user.pk or user.username}"


@receiver(post_save, sender=User)
def ensure_player_profile(sender, instance, created, **kwargs):
    """
    Create a PlayerProfile when a user is created.

    Important:
    During first setup, createsuperuser can run before the core table exists
    if migrations were missing/not applied. In that case, do not crash.
    post_migrate will backfill missing profiles after migrations.
    """
    if not created:
        return

    try:
        PlayerProfile.objects.get_or_create(
            user=instance,
            defaults={"konami_id": default_konami_id(instance)},
        )
        NotificationPreference.objects.get_or_create(user=instance)
    except (OperationalError, ProgrammingError, IntegrityError):
        return


@receiver(post_migrate)
def ensure_missing_player_profiles(sender, app_config=None, **kwargs):
    """
    After migrations, make sure every existing User has a PlayerProfile.
    """
    if app_config is not None and app_config.label != "core":
        return

    try:
        UserModel = apps.get_model("auth", "User")
        ProfileModel = apps.get_model("core", "PlayerProfile")
        PreferenceModel = apps.get_model("core", "NotificationPreference")

        for user in UserModel.objects.all():
            ProfileModel.objects.get_or_create(
                user=user,
                defaults={"konami_id": default_konami_id(user)},
            )
            PreferenceModel.objects.get_or_create(user=user)
    except (OperationalError, ProgrammingError, IntegrityError):
        return
