from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


def feed_photo_path(instance, filename):
    return f'feed/{instance.author_id}/{filename}'


def profile_photo_path(instance, filename):
    return f'profiles/{instance.user_id}/{filename}'


def validate_site_image(file_obj):
    max_size = 5 * 1024 * 1024
    allowed = {'.jpg', '.jpeg', '.png', '.webp'}
    name = (file_obj.name or '').lower()
    ext = name[name.rfind('.'):] if '.' in name else ''
    if file_obj.size > max_size:
        raise ValidationError('The uploaded image must not exceed 5 MB.')
    if ext not in allowed:
        raise ValidationError('Only JPG, PNG or WEBP images are allowed.')


def validate_feed_photo(file_obj):
    validate_site_image(file_obj)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PlayerProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='player_profile')
    konami_id = models.CharField(max_length=64, unique=True)
    full_name = models.CharField(max_length=180, blank=True)
    profile_photo = models.FileField(upload_to=profile_photo_path, validators=[validate_site_image], blank=True, null=True)
    city = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    main_play_style = models.CharField(max_length=120, blank=True)
    favorite_formation = models.CharField(max_length=60, blank=True)
    is_public = models.BooleanField(default=True)

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return self.user.username

    def get_absolute_url(self):
        return reverse('player_detail', kwargs={'username': self.user.username})

    @property
    def initials(self):
        source = self.full_name or self.user.get_full_name() or self.user.username
        parts = [part[0] for part in source.split() if part]
        return ''.join(parts[:2]).upper() or self.user.username[:1].upper()


class League(TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]
    VISIBILITY_CHOICES = [
        ('private', 'Private'),
        ('public', 'Public'),
    ]
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default='public')
    organizer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='organized_leagues')

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'league'
            slug = base
            index = 2
            while League.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{index}'
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('league_detail', kwargs={'slug': self.slug})

    @property
    def is_public_active(self):
        return self.visibility == 'public' and self.status == 'active'


class LeagueMembership(TimeStampedModel):
    ROLE_CHOICES = [('player', 'Player'), ('manager', 'Manager')]
    STATUS_CHOICES = [('active', 'Active'), ('inactive', 'Inactive')]
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='memberships')
    player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='league_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='player')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    class Meta:
        unique_together = [('league', 'player')]
        ordering = ['league__name', 'player__user__username']

    def __str__(self):
        return f'{self.player} in {self.league}'


class LeagueJoinRequest(TimeStampedModel):
    STATUS_CHOICES = [('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')]
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='join_requests')
    player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='league_join_requests')
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_join_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('league', 'player')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.player} -> {self.league} ({self.status})'


class Season(TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('registration_open', 'Registration open'),
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('archived', 'Archived'),
    ]
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='seasons')
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, blank=True)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='registration_open')
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    promotions_applied = models.BooleanField(default=False)

    class Meta:
        unique_together = [('league', 'slug')]
        ordering = ['-start_date', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'season'
            slug = base
            index = 2
            while Season.objects.filter(league=self.league, slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{index}'
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.league} — {self.name}'

    @property
    def is_public_visible(self):
        return self.status in {'registration_open', 'active', 'completed', 'archived'} and self.league.is_public_active


class Division(TimeStampedModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name='divisions')
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, blank=True)
    order = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [('season', 'slug')]
        ordering = ['season__league__name', 'season__name', 'order', 'name']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'division'
            slug = base
            index = 2
            while Division.objects.filter(season=self.season, slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{index}'
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.season} — {self.name}'

    def get_absolute_url(self):
        return reverse('division_detail', kwargs={'pk': self.pk})


class DivisionMembership(TimeStampedModel):
    division = models.ForeignKey(Division, on_delete=models.CASCADE, related_name='memberships')
    player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='division_memberships')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('division', 'player')]
        ordering = ['division__name', 'player__user__username']

    def __str__(self):
        return f'{self.player} in {self.division}'


class Match(TimeStampedModel):
    TYPE_CHOICES = [('official', 'Official'), ('friendly', 'Friendly')]
    STATUS_CHOICES = [('scheduled', 'Scheduled'), ('played', 'Played'), ('cancelled', 'Cancelled')]
    match_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='official')
    league = models.ForeignKey(League, on_delete=models.CASCADE, related_name='matches', null=True, blank=True)
    season = models.ForeignKey(Season, on_delete=models.SET_NULL, related_name='matches', null=True, blank=True)
    division = models.ForeignKey(Division, on_delete=models.SET_NULL, related_name='matches', null=True, blank=True)
    home_player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='home_matches')
    away_player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='away_matches')
    scheduled_at = models.DateTimeField(null=True, blank=True)
    played_at = models.DateTimeField(null=True, blank=True)
    round_number = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    home_score = models.PositiveIntegerField(null=True, blank=True)
    away_score = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_matches')

    class Meta:
        ordering = ['-scheduled_at', '-created_at']

    def __str__(self):
        return f'{self.home_player} vs {self.away_player}'

    @property
    def has_score(self):
        return self.home_score is not None and self.away_score is not None

    def clean_scores_for_played(self):
        if self.status == 'played' and not self.has_score:
            raise ValueError('A played match must have a score.')


class FriendlyMatchRequest(TimeStampedModel):
    STATUS_CHOICES = [('pending', 'Pending'), ('accepted', 'Accepted'), ('declined', 'Declined'), ('cancelled', 'Cancelled')]
    requester = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='friendly_requests_sent')
    opponent = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='friendly_requests_received')
    message = models.TextField(blank=True)
    proposed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    match = models.ForeignKey(Match, on_delete=models.SET_NULL, null=True, blank=True, related_name='friendly_request')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.requester} -> {self.opponent} ({self.status})'


class NewsPost(TimeStampedModel):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='news_posts')
    content = models.TextField()
    photo = models.FileField(upload_to=feed_photo_path, validators=[validate_feed_photo], blank=True, null=True)
    is_pinned = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_pinned', '-created_at']

    def __str__(self):
        return f'Post by {self.author.username}'

    @property
    def like_count(self):
        return self.reactions.filter(reaction=NewsReaction.LIKE).count()

    @property
    def dislike_count(self):
        return self.reactions.filter(reaction=NewsReaction.DISLIKE).count()

    def delete(self, *args, **kwargs):
        photo = self.photo
        super().delete(*args, **kwargs)
        if photo:
            photo.delete(save=False)


class NewsComment(TimeStampedModel):
    post = models.ForeignKey(NewsPost, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='news_comments')
    content = models.TextField()

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Comment by {self.author.username}'


class NewsLike(TimeStampedModel):
    post = models.ForeignKey(NewsPost, on_delete=models.CASCADE, related_name='likes')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='news_likes')

    class Meta:
        unique_together = [('post', 'user')]

    def __str__(self):
        return f'{self.user.username} likes {self.post_id}'


class NewsReaction(TimeStampedModel):
    LIKE = 'like'
    DISLIKE = 'dislike'
    REACTION_CHOICES = [(LIKE, 'Like'), (DISLIKE, 'Dislike')]
    post = models.ForeignKey(NewsPost, on_delete=models.CASCADE, related_name='reactions')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='news_reactions')
    reaction = models.CharField(max_length=10, choices=REACTION_CHOICES)

    class Meta:
        unique_together = [('post', 'user')]

    def __str__(self):
        return f'{self.user.username} {self.reaction} {self.post_id}'


class NotificationPreference(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='notification_preference')
    enabled = models.BooleanField(default=False)
    friendly_requests = models.BooleanField(default=True)
    match_updates = models.BooleanField(default=True)
    comments = models.BooleanField(default=True)
    system_updates = models.BooleanField(default=True)

    class Meta:
        ordering = ['user__username']

    def __str__(self):
        return f'Notification preferences for {self.user.username}'


class Notification(TimeStampedModel):
    TYPE_CHOICES = [
        ('friendly_request', 'Friendly request'),
        ('match_update', 'Match update'),
        ('comment', 'Comment'),
        ('system', 'System'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=160)
    message = models.TextField()
    notification_type = models.CharField(max_length=32, choices=TYPE_CHOICES, default='system')
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} -> {self.user.username}'


class Tournament(TimeStampedModel):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('groups_ready', 'Groups ready'),
        ('group_stage', 'Group stage'),
        ('knockout', 'Knockout'),
        ('completed', 'Completed'),
    ]
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    champion = models.ForeignKey(PlayerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='tournament_wins')
    max_participants = models.PositiveIntegerField(default=32)
    groups_generated = models.BooleanField(default=False)
    group_fixtures_generated = models.BooleanField(default=False)
    knockout_generated = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or 'tournament'
            slug = base
            index = 2
            while Tournament.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{index}'
                index += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('tournament_detail', kwargs={'slug': self.slug})


class TournamentParticipant(TimeStampedModel):
    STATUS_CHOICES = [('selected', 'Selected'), ('reserve', 'Reserve')]
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='participants')
    player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='tournament_entries')
    seed = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='selected')

    class Meta:
        unique_together = [('tournament', 'player')]
        ordering = ['status', 'seed', 'player__user__username']

    def __str__(self):
        return f'{self.player} in {self.tournament}'


class TournamentGroup(TimeStampedModel):
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=20)

    class Meta:
        unique_together = [('tournament', 'name')]
        ordering = ['name']

    def __str__(self):
        return f'{self.tournament} Group {self.name}'


class TournamentGroupMembership(TimeStampedModel):
    group = models.ForeignKey(TournamentGroup, on_delete=models.CASCADE, related_name='memberships')
    participant = models.ForeignKey(TournamentParticipant, on_delete=models.CASCADE, related_name='group_memberships')

    class Meta:
        unique_together = [('group', 'participant')]
        ordering = ['group__name', 'participant__player__user__username']

    def __str__(self):
        return f'{self.participant.player} - {self.group.name}'


class TournamentMatch(TimeStampedModel):
    STAGE_CHOICES = [
        ('group', 'Group'),
        ('round_of_16', 'Round of 16'),
        ('quarter_final', 'Quarter-final'),
        ('semi_final', 'Semi-final'),
        ('final', 'Final'),
    ]
    STATUS_CHOICES = [('scheduled', 'Scheduled'), ('played', 'Played')]
    tournament = models.ForeignKey(Tournament, on_delete=models.CASCADE, related_name='matches')
    group = models.ForeignKey(TournamentGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='matches')
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='group')
    round_number = models.PositiveIntegerField(default=1)
    home_player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='tournament_home_matches')
    away_player = models.ForeignKey(PlayerProfile, on_delete=models.CASCADE, related_name='tournament_away_matches')
    home_score = models.PositiveIntegerField(null=True, blank=True)
    away_score = models.PositiveIntegerField(null=True, blank=True)
    winner = models.ForeignKey(PlayerProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='tournament_match_wins')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')

    class Meta:
        ordering = ['round_number', 'stage', 'group__name', 'id']

    @property
    def has_score(self):
        return self.home_score is not None and self.away_score is not None

    def __str__(self):
        return f'{self.tournament}: {self.home_player} vs {self.away_player}'
