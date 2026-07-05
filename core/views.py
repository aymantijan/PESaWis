import json
from datetime import timedelta
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.contrib.staticfiles import finders
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    CalendarGenerationForm,
    DivisionForm,
    DivisionMembershipForm,
    FriendlyMatchRequestForm,
    LeagueForm,
    MatchForm,
    NewsCommentForm,
    NewsPostForm,
    NotificationPreferenceForm,
    PlayerProfileForm,
    PrivateTournamentForm,
    SeasonForm,
    SignupForm,
    TournamentForm,
    TournamentInviteForm,
    TournamentMatchScoreForm,
    TournamentParticipantForm,
)
from .models import (
    Division,
    DivisionMembership,
    FriendlyMatchRequest,
    League,
    LeagueJoinRequest,
    LeagueMembership,
    LiveStream,
    Match,
    NewsComment,
    NewsPost,
    NewsReaction,
    Notification,
    NotificationPreference,
    PlayerProfile,
    PushSubscription,
    Season,
    StreamSignal,
    Tournament,
    TournamentInvite,
    TournamentMatch,
    TournamentParticipant,
)
from .push import send_web_push
from .scheduling import round_robin_rounds
from . import tournaments as tournament_logic
from .utils import best_defenders, compute_player_stats, division_standings, season_outcomes, top_scorers


def staff_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to perform this action.')
            return redirect('login')
        if not (request.user.is_staff or request.user.is_superuser):
            messages.error(request, 'You do not have permission to perform this action.')
            return redirect('home')
        return view_func(request, *args, **kwargs)
    return wrapper


def tournament_manager_required(view_func):
    """Allow staff or the tournament's own creator to manage it (used for private, friend-run tournaments)."""
    @wraps(view_func)
    def wrapper(request, slug, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to perform this action.')
            return redirect('login')
        tournament = get_object_or_404(Tournament, slug=slug)
        if not tournament.can_manage(request.user):
            messages.error(request, 'You do not have permission to manage this tournament.')
            return redirect('tournament_detail', slug=slug)
        return view_func(request, slug, *args, **kwargs)
    return wrapper


def add_form_error_messages(request, form):
    seen = set()
    for errors in form.errors.values():
        for error in errors:
            if error not in seen:
                messages.error(request, error)
                seen.add(error)


def notification_allowed(preference, notification_type):
    if not preference.enabled:
        return False
    if notification_type == 'friendly_request':
        return preference.friendly_requests
    if notification_type == 'match_update':
        return preference.match_updates
    if notification_type == 'comment':
        return preference.comments
    if notification_type == 'tag':
        return preference.tags
    if notification_type == 'tournament_invite':
        return preference.tournament_invites
    return preference.system_updates


def create_notification(user, title, message, notification_type='system', link=''):
    preference, _ = NotificationPreference.objects.get_or_create(user=user)
    if not notification_allowed(preference, notification_type):
        return None
    notification = Notification.objects.create(
        user=user,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link,
    )
    send_web_push(user, title, message, link)
    return notification


def notify_tagged_users(users, actor, title, link):
    for tagged_user in users:
        if tagged_user == actor:
            continue
        create_notification(tagged_user, title, f'{actor.username} tagged you.', 'tag', link)


def notify_match_scheduled(match):
    link = '/calendar/'
    for profile in [match.home_player, match.away_player]:
        create_notification(
            profile.user,
            'Match scheduled',
            f'{match.home_player.user.username} vs {match.away_player.user.username} has been scheduled.',
            'match_update',
            link,
        )


def service_worker(request):
    path = finders.find('core/js/sw.js')
    with open(path, 'rb') as handle:
        return HttpResponse(handle.read(), content_type='application/javascript')


def public_leagues():
    return League.objects.filter(visibility='public', status='active')


def home(request):
    leagues = public_leagues().annotate(member_count=Count('memberships')).order_by('name')[:6]
    posts = NewsPost.objects.select_related('author').prefetch_related('comments', 'reactions')[:5]
    upcoming = Match.objects.select_related('home_player__user', 'away_player__user').filter(status='scheduled').order_by('scheduled_at')[:6]
    return render(request, 'core/home.html', {'leagues': leagues, 'posts': posts, 'upcoming': upcoming, 'scorers': top_scorers(5)})


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, 'Created successfully.')
        return redirect('dashboard')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/signup.html', {'form': form})


@login_required
def dashboard(request):
    profile = request.user.player_profile
    matches = Match.objects.select_related('home_player__user', 'away_player__user').filter(Q(home_player=profile) | Q(away_player=profile))[:10]
    incoming = FriendlyMatchRequest.objects.select_related('requester__user').filter(opponent=profile, status='pending')
    outgoing = FriendlyMatchRequest.objects.select_related('opponent__user').filter(requester=profile)[:10]
    joins = LeagueJoinRequest.objects.select_related('league').filter(player=profile)[:10]
    tournament_invites = TournamentInvite.objects.select_related('tournament', 'invited_by').filter(invitee=profile, status='pending')
    return render(request, 'core/dashboard.html', {'profile': profile, 'matches': matches, 'incoming': incoming, 'outgoing': outgoing, 'joins': joins, 'tournament_invites': tournament_invites})


@login_required
def notifications(request):
    preference, _ = NotificationPreference.objects.get_or_create(user=request.user)
    form = NotificationPreferenceForm(request.POST or None, instance=preference)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Notification preferences updated successfully.')
        return redirect('notifications')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    items = request.user.notifications.all()[:50]
    return render(request, 'core/notifications.html', {
        'form': form,
        'preference': preference,
        'notifications': items,
    })


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(Notification, pk=pk, user=request.user)
    notification.is_read = True
    notification.save(update_fields=['is_read', 'updated_at'])
    messages.success(request, 'Updated successfully.')
    return redirect('notifications')


@login_required
@require_POST
def push_subscribe(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
        endpoint = payload['endpoint']
        keys = payload['keys']
        p256dh = keys['p256dh']
        auth = keys['auth']
    except (KeyError, ValueError, TypeError):
        return HttpResponseBadRequest('Invalid subscription payload.')
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={'user': request.user, 'p256dh': p256dh, 'auth': auth},
    )
    return JsonResponse({'status': 'subscribed'})


@login_required
@require_POST
def push_unsubscribe(request):
    try:
        payload = json.loads(request.body.decode('utf-8'))
        endpoint = payload['endpoint']
    except (KeyError, ValueError, TypeError):
        return HttpResponseBadRequest('Invalid payload.')
    PushSubscription.objects.filter(endpoint=endpoint, user=request.user).delete()
    return JsonResponse({'status': 'unsubscribed'})


@login_required
def edit_profile(request):
    profile = request.user.player_profile
    form = PlayerProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        profile = form.save()
        names = profile.full_name.split(' ', 1)
        request.user.first_name = names[0] if names else ''
        request.user.last_name = names[1] if len(names) > 1 else ''
        request.user.save(update_fields=['first_name', 'last_name'])
        messages.success(request, 'Updated successfully.')
        return redirect('dashboard')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Edit profile', 'form': form})


def rules(request):
    lang = request.GET.get('lang', 'en')
    if lang not in {'en', 'fr', 'ar'}:
        lang = 'en'
    return render(request, 'core/rules.html', {'active_lang': lang})


def league_list(request):
    q = request.GET.get('q', '').strip()
    leagues = public_leagues().annotate(member_count=Count('memberships'), season_count=Count('seasons'))
    if q:
        leagues = leagues.filter(Q(name__icontains=q) | Q(description__icontains=q))
    return render(request, 'core/league_list.html', {'leagues': leagues, 'q': q})


def league_detail(request, slug):
    league = get_object_or_404(public_leagues(), slug=slug)
    seasons = league.seasons.exclude(status='draft').prefetch_related('divisions')
    divisions = Division.objects.filter(season__league=league, season__status__in=['registration_open', 'active', 'completed', 'archived'])
    matches = league.matches.select_related('home_player__user', 'away_player__user', 'division').order_by('-scheduled_at')[:10]
    join_state = None
    if request.user.is_authenticated:
        profile = request.user.player_profile
        if LeagueMembership.objects.filter(league=league, player=profile, status='active').exists():
            join_state = 'member'
        elif LeagueJoinRequest.objects.filter(league=league, player=profile, status='pending').exists():
            join_state = 'pending'
    return render(request, 'core/league_detail.html', {'league': league, 'seasons': seasons, 'divisions': divisions, 'matches': matches, 'join_state': join_state})


@login_required
def request_to_join_league(request, slug):
    league = get_object_or_404(public_leagues(), slug=slug)
    profile = request.user.player_profile
    if LeagueMembership.objects.filter(league=league, player=profile, status='active').exists():
        messages.info(request, 'You are already a member of this league.')
        return redirect('league_detail', slug=slug)
    request_obj, created = LeagueJoinRequest.objects.get_or_create(league=league, player=profile, defaults={'message': ''})
    if created:
        messages.success(request, 'Join request sent.')
    elif request_obj.status == 'rejected':
        request_obj.status = 'pending'
        request_obj.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Join request sent again.')
    else:
        messages.info(request, f'Your request is already {request_obj.status}.')
    return redirect('league_detail', slug=slug)


def division_list(request):
    divisions = Division.objects.select_related('season__league').filter(season__league__visibility='public', season__league__status='active').annotate(member_count=Count('memberships'))
    return render(request, 'core/division_list.html', {'divisions': divisions})


def division_detail(request, pk):
    division = get_object_or_404(Division.objects.select_related('season__league'), pk=pk)
    members = PlayerProfile.objects.filter(division_memberships__division=division, division_memberships__is_active=True).select_related('user')
    matches = Match.objects.select_related('home_player__user', 'away_player__user').filter(division=division)
    standings = division_standings(division)
    return render(request, 'core/division_detail.html', {'division': division, 'members': members, 'matches': matches, 'standings': standings})


def calendar(request):
    matches = Match.objects.select_related('home_player__user', 'away_player__user', 'league', 'division', 'season').filter(Q(league__visibility='public', league__status='active') | Q(match_type='friendly'))
    status = request.GET.get('status', '')
    division_id = request.GET.get('division', '')
    season_id = request.GET.get('season', '')
    if status:
        matches = matches.filter(status=status)
    if division_id:
        matches = matches.filter(division_id=division_id)
    if season_id:
        matches = matches.filter(season_id=season_id)
    return render(request, 'core/calendar.html', {
        'matches': matches.order_by('round_number', 'scheduled_at', 'id'),
        'status': status,
        'division_id': division_id,
        'season_id': season_id,
        'divisions': Division.objects.select_related('season__league'),
        'seasons': Season.objects.select_related('league'),
    })


def standings(request):
    divisions = Division.objects.select_related('season__league').all()
    selected = get_object_or_404(Division, pk=request.GET.get('division')) if request.GET.get('division') else divisions.first()
    table = division_standings(selected) if selected else []
    return render(request, 'core/standings.html', {'divisions': divisions, 'selected': selected, 'standings': table})


def rankings(request):
    matches = Match.objects.select_related('home_player__user', 'away_player__user').filter(match_type='official', status='played')
    stats = compute_player_stats(matches)
    return render(request, 'core/rankings.html', {
        'best_players': stats[:20],
        'top_scorers': sorted(stats, key=lambda x: (-x['goals_for'], -x['points'], x['player'].user.username.lower()))[:20],
        'best_defenders': best_defenders(20),
    })


def player_list(request):
    q = request.GET.get('q', '').strip()
    players = PlayerProfile.objects.select_related('user').filter(is_public=True)
    if q:
        players = players.filter(Q(user__username__icontains=q) | Q(full_name__icontains=q) | Q(konami_id__icontains=q))
    return render(request, 'core/player_list.html', {'players': players, 'q': q})


def player_detail(request, username):
    user = get_object_or_404(User, username=username)
    profile = get_object_or_404(PlayerProfile, user=user, is_public=True)
    matches = Match.objects.select_related('home_player__user', 'away_player__user', 'division').filter(Q(home_player=profile) | Q(away_player=profile))[:20]
    stat = compute_player_stats([m for m in matches if m.status == 'played'], players=[profile])[0]
    division_membership = profile.division_memberships.select_related('division__season').filter(is_active=True).order_by('division__season__start_date').last()
    incoming = FriendlyMatchRequest.objects.select_related('requester__user', 'opponent__user').filter(Q(requester=profile) | Q(opponent=profile))[:10]
    posts = profile.user.news_posts.all()[:5]
    return render(request, 'core/player_detail.html', {'profile': profile, 'matches': matches, 'stat': stat, 'division_membership': division_membership, 'friendly_requests': incoming, 'posts': posts})


@login_required
def request_friendly_match(request, username):
    opponent_user = get_object_or_404(User, username=username)
    opponent = opponent_user.player_profile
    requester = request.user.player_profile
    if requester == opponent:
        messages.error(request, 'You cannot request a match against yourself.')
        return redirect('player_detail', username=username)
    form = FriendlyMatchRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        friendly = form.save(commit=False)
        friendly.requester = requester
        friendly.opponent = opponent
        friendly.save()
        create_notification(
            opponent.user,
            'Friendly request received',
            f'{requester.user.username} sent you a friendly match request.',
            'friendly_request',
            '/dashboard/',
        )
        messages.success(request, 'Friendly request sent successfully.')
        return redirect('player_detail', username=username)
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': f'Request friendly match vs {username}', 'form': form})


@login_required
@require_POST
def handle_friendly_request(request, pk, action):
    profile = request.user.player_profile
    if action == 'cancel':
        req = get_object_or_404(FriendlyMatchRequest, pk=pk, requester=profile, status='pending')
        req.status = 'cancelled'
        req.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Updated successfully.')
        return redirect('dashboard')
    req = get_object_or_404(FriendlyMatchRequest, pk=pk, opponent=profile, status='pending')
    if action == 'accept':
        match = Match.objects.create(match_type='friendly', home_player=req.requester, away_player=req.opponent, scheduled_at=req.proposed_at, status='scheduled', created_by=request.user)
        req.status = 'accepted'
        req.match = match
        req.save(update_fields=['status', 'match', 'updated_at'])
        create_notification(req.requester.user, 'Friendly request accepted', f'{req.opponent.user.username} accepted your friendly request.', 'friendly_request', '/dashboard/')
        notify_match_scheduled(match)
        messages.success(request, 'Updated successfully.')
    elif action == 'decline':
        req.status = 'declined'
        req.save(update_fields=['status', 'updated_at'])
        create_notification(req.requester.user, 'Friendly request declined', f'{req.opponent.user.username} declined your friendly request.', 'friendly_request', '/dashboard/')
        messages.success(request, 'Updated successfully.')
    return redirect('dashboard')


def active_streams():
    """Streams currently live with a recent broadcaster heartbeat.

    The window is generous (5 minutes) because the broadcaster's browser is
    backgrounded while they play, which throttles the heartbeat polling.
    """
    cutoff = timezone.now() - timedelta(minutes=5)
    return LiveStream.objects.select_related('streamer').filter(status='live', updated_at__gte=cutoff)


@login_required
@require_POST
def stream_start(request):
    title = request.POST.get('title', '').strip() or f"Live match — {request.user.username}"
    now = timezone.now()
    LiveStream.objects.filter(streamer=request.user, status='live').update(status='ended', ended_at=now)
    stream = LiveStream.objects.create(streamer=request.user, title=title[:160])
    return redirect('stream_broadcast', pk=stream.pk)


@login_required
def stream_broadcast(request, pk):
    stream = get_object_or_404(LiveStream, pk=pk, streamer=request.user)
    return render(request, 'core/stream_broadcast.html', {'stream': stream})


@login_required
def stream_watch(request, pk):
    stream = get_object_or_404(LiveStream.objects.select_related('streamer'), pk=pk)
    return render(request, 'core/stream_watch.html', {'stream': stream})


@login_required
@require_POST
def stream_stop(request, pk):
    stream = get_object_or_404(LiveStream, pk=pk, streamer=request.user)
    stream.status = 'ended'
    stream.ended_at = timezone.now()
    stream.save(update_fields=['status', 'ended_at', 'updated_at'])
    stream.signals.all().delete()
    messages.success(request, 'Stream ended. Nothing was recorded or stored.')
    return redirect('news_feed')


@login_required
@require_POST
def stream_signal(request, pk):
    stream = get_object_or_404(LiveStream, pk=pk, status='live')
    try:
        payload = json.loads(request.body.decode('utf-8'))
        kind = payload['kind']
        target = payload['target']
        peer_id = payload.get('peer_id', '')[:64]
        data = payload.get('payload', '')
    except (KeyError, ValueError, TypeError):
        return HttpResponseBadRequest('Invalid signal payload.')
    if kind not in {'join', 'offer', 'answer', 'ice', 'leave'} or target not in {'broadcaster', 'viewer'}:
        return HttpResponseBadRequest('Invalid signal.')
    if target == 'viewer' and request.user != stream.streamer:
        return HttpResponseBadRequest('Only the broadcaster signals viewers.')
    signal = StreamSignal.objects.create(
        stream=stream, peer_id=peer_id, target=target, kind=kind,
        payload=data if isinstance(data, str) else json.dumps(data),
    )
    return JsonResponse({'id': signal.id})


@login_required
def stream_poll(request, pk):
    stream = get_object_or_404(LiveStream, pk=pk)
    role = request.GET.get('role', 'viewer')
    peer_id = request.GET.get('peer_id', '')[:64]
    try:
        after = int(request.GET.get('after', 0))
    except ValueError:
        after = 0
    signals = stream.signals.filter(id__gt=after)
    if role == 'broadcaster':
        if request.user != stream.streamer:
            return HttpResponseBadRequest('Not your stream.')
        signals = signals.filter(target='broadcaster')
        # heartbeat keeps the stream listed as live
        stream.save(update_fields=['updated_at'])
    else:
        signals = signals.filter(target='viewer', peer_id=peer_id)
    return JsonResponse({
        'status': stream.status,
        'signals': [
            {'id': s.id, 'kind': s.kind, 'peer_id': s.peer_id, 'payload': s.payload}
            for s in signals[:100]
        ],
    })


def news_feed(request):
    form = NewsPostForm()
    if request.method == 'POST':
        if not request.user.is_authenticated:
            messages.error(request, 'You must be logged in to perform this action.')
            return redirect('login')
        form = NewsPostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            form.save_m2m()
            notify_tagged_users(post.tagged_users.all(), request.user, f'{request.user.username} tagged you in a post', '/feed/')
            messages.success(request, 'Post published successfully.')
            return redirect('news_feed')
        add_form_error_messages(request, form)
    posts = NewsPost.objects.select_related('author').prefetch_related('comments__author', 'comments__tagged_users', 'reactions', 'tagged_users')
    return render(request, 'core/news_feed.html', {
        'posts': posts,
        'form': form,
        'comment_form': NewsCommentForm(),
        'live_streams': active_streams(),
    })


@login_required
def edit_post(request, pk):
    post = get_object_or_404(NewsPost, pk=pk)
    if post.author != request.user:
        messages.error(request, 'You do not have permission to edit this post.')
        return redirect('news_feed')
    form = NewsPostForm(request.POST or None, request.FILES or None, instance=post)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Post updated successfully.')
        return redirect('news_feed')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Edit post', 'form': form})


@login_required
@require_POST
def delete_post(request, pk):
    post = get_object_or_404(NewsPost, pk=pk)
    if post.author != request.user:
        messages.error(request, 'You do not have permission to delete this post.')
        return redirect('news_feed')
    post.delete()
    messages.success(request, 'Post deleted successfully.')
    return redirect('news_feed')


@login_required
@require_POST
def add_comment(request, pk):
    post = get_object_or_404(NewsPost, pk=pk)
    form = NewsCommentForm(request.POST)
    if form.is_valid():
        comment = NewsComment.objects.create(post=post, author=request.user, content=form.cleaned_data['content'])
        comment.tagged_users.set(form.cleaned_data.get('tagged_users', []))
        if post.author != request.user:
            create_notification(
                post.author,
                'New comment',
                f'{request.user.username} commented on your post.',
                'comment',
                '/feed/',
            )
        notify_tagged_users(comment.tagged_users.all(), request.user, f'{request.user.username} tagged you in a comment', '/feed/')
        messages.success(request, 'Comment added successfully.')
    else:
        add_form_error_messages(request, form)
    return redirect('news_feed')


@login_required
def edit_comment(request, pk):
    comment = get_object_or_404(NewsComment.objects.select_related('author'), pk=pk)
    if comment.author != request.user:
        messages.error(request, 'You do not have permission to edit this comment.')
        return redirect('news_feed')
    form = NewsCommentForm(request.POST or None, instance=comment)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Comment updated successfully.')
        return redirect('news_feed')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Edit comment', 'form': form})


@login_required
@require_POST
def delete_comment(request, pk):
    comment = get_object_or_404(NewsComment.objects.select_related('author'), pk=pk)
    if comment.author != request.user:
        messages.error(request, 'You do not have permission to delete this comment.')
        return redirect('news_feed')
    comment.delete()
    messages.success(request, 'Comment deleted successfully.')
    return redirect('news_feed')


@login_required
@require_POST
def react_post(request, pk, reaction):
    post = get_object_or_404(NewsPost, pk=pk)
    if reaction not in {'like', 'dislike'}:
        messages.error(request, 'Invalid reaction.')
        return redirect('news_feed')
    existing = NewsReaction.objects.filter(post=post, user=request.user).first()
    if existing and existing.reaction == reaction:
        existing.delete()
    elif existing:
        existing.reaction = reaction
        existing.save(update_fields=['reaction', 'updated_at'])
    else:
        NewsReaction.objects.create(post=post, user=request.user, reaction=reaction)
    return redirect('news_feed')


@staff_required
def management_dashboard(request):
    pending_requests = LeagueJoinRequest.objects.select_related('league', 'player__user').filter(status='pending')
    pending_friendly_requests = FriendlyMatchRequest.objects.select_related('requester__user', 'opponent__user').filter(status='pending')[:10]
    pending_notifications = Notification.objects.select_related('user').filter(is_read=False)[:10]
    matches = Match.objects.select_related('home_player__user', 'away_player__user').order_by('-created_at')[:20]
    return render(request, 'core/management_dashboard.html', {
        'pending_requests': pending_requests,
        'pending_friendly_requests': pending_friendly_requests,
        'pending_notifications': pending_notifications,
        'matches': matches,
        'league_count': League.objects.count(),
        'player_count': PlayerProfile.objects.count(),
        'match_count': Match.objects.count(),
        'tournament_count': Tournament.objects.count(),
    })


@staff_required
def create_league(request):
    form = LeagueForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        league = form.save(commit=False)
        league.organizer = request.user
        league.save()
        messages.success(request, 'Created successfully.')
        return redirect('league_detail', slug=league.slug)
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Create league', 'form': form})


@staff_required
def create_season(request):
    form = SeasonForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        season = form.save()
        messages.success(request, 'Created successfully.')
        return redirect('league_detail', slug=season.league.slug)
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Create season', 'form': form})


@staff_required
def create_division(request):
    form = DivisionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        division = form.save()
        messages.success(request, 'Created successfully.')
        return redirect('division_detail', pk=division.pk)
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Create division', 'form': form})


@staff_required
def create_division_membership(request):
    form = DivisionMembershipForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Created successfully.')
        return redirect('management_dashboard')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Assign player to division', 'form': form})


@staff_required
def create_calendar(request):
    form = CalendarGenerationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        division = form.cleaned_data['division']
        players = list(PlayerProfile.objects.filter(division_memberships__division=division, division_memberships__is_active=True).select_related('user'))
        if len(players) < 2:
            messages.error(request, 'This division needs at least 2 players to generate a calendar.')
            return redirect('create_calendar')
        if Match.objects.filter(division=division, match_type='official').exists():
            messages.error(request, 'Calendar already exists for this division.')
            return redirect('calendar')
        start_date = form.cleaned_data.get('start_date')
        days_between = form.cleaned_data.get('days_between_rounds') or 7
        schedule = round_robin_rounds(players, form.cleaned_data['double_round_robin'])
        with transaction.atomic():
            for round_number, home, away in schedule:
                scheduled_at = None
                if start_date:
                    scheduled_at = timezone.make_aware(
                        timezone.datetime.combine(start_date, timezone.datetime.min.time()).replace(hour=20)
                    ) + timedelta(days=(round_number - 1) * days_between)
                Match.objects.create(
                    match_type='official', league=division.season.league, season=division.season,
                    division=division, home_player=home, away_player=away,
                    round_number=round_number, scheduled_at=scheduled_at,
                    status='scheduled', created_by=request.user,
                )
        round_total = max((r for r, _, _ in schedule), default=0)
        messages.success(request, f'Calendar created: {len(schedule)} matches over {round_total} rounds — every player plays once per round.')
        return redirect('calendar')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Create Calendar', 'form': form})


@staff_required
def create_match(request):
    form = MatchForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        match = form.save(commit=False)
        match.created_by = request.user
        if match.division:
            match.league = match.division.season.league
            match.season = match.division.season
        match.save()
        notify_match_scheduled(match)
        messages.success(request, 'Created successfully.')
        return redirect('calendar')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Create match', 'form': form})


@staff_required
def update_match_score(request, pk):
    match = get_object_or_404(Match, pk=pk)
    form = MatchForm(request.POST or None, instance=match)
    if request.method == 'POST' and form.is_valid():
        match = form.save(commit=False)
        if match.status == 'played' and not match.played_at:
            match.played_at = timezone.now()
        match.save()
        messages.success(request, 'Score saved successfully.')
        return redirect('calendar')
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Update match / score', 'form': form})


@staff_required
@require_POST
def handle_join_request(request, pk, action):
    req = get_object_or_404(LeagueJoinRequest, pk=pk, status='pending')
    if action == 'accept':
        LeagueMembership.objects.update_or_create(league=req.league, player=req.player, defaults={'status': 'active', 'role': 'player'})
        req.status = 'accepted'
        messages.success(request, f'{req.player} accepted into {req.league}.')
    elif action == 'reject':
        req.status = 'rejected'
        messages.info(request, 'Join request rejected.')
    req.reviewed_by = request.user
    req.reviewed_at = timezone.now()
    req.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])
    return redirect('management_dashboard')


def season_outcome_view(request, season_id):
    season = get_object_or_404(Season.objects.select_related('league'), pk=season_id)
    return render(request, 'core/season_outcome.html', {'season': season, 'rows': season_outcomes(season)})


@staff_required
@require_POST
def apply_promotion_relegation(request, season_id):
    season = get_object_or_404(Season, pk=season_id, status='completed')
    if season.promotions_applied:
        messages.error(request, 'Promotion/relegation has already been applied.')
        return redirect('season_outcome', season_id=season.pk)
    rows = season_outcomes(season)
    moved = 0
    with transaction.atomic():
        for row in rows:
            if row['outcome'] in {'Promoted', 'Relegated'} and row['target']:
                DivisionMembership.objects.filter(division=row['division'], player=row['player']).update(is_active=False)
                DivisionMembership.objects.update_or_create(division=row['target'], player=row['player'], defaults={'is_active': True})
                moved += 1
                create_notification(
                    row['player'].user,
                    'Promotion' if row['outcome'] == 'Promoted' else 'Relegation',
                    f'You are {"promoted to" if row["outcome"] == "Promoted" else "relegated to"} {row["target"].name} for the next stage.',
                    'system',
                    '/standings/',
                )
            elif row['outcome'] == 'Champion':
                create_notification(row['player'].user, 'Champion!', f'You won {row["division"].name} — league champion of {season.name}!', 'system', '/standings/')
        season.promotions_applied = True
        season.save(update_fields=['promotions_applied', 'updated_at'])
    messages.success(request, f'Promotion/relegation applied ({moved} players moved).')
    return redirect('season_outcome', season_id=season.pk)


def tournament_list(request):
    all_tournaments = Tournament.objects.select_related('created_by').prefetch_related('invites')
    tournaments = [t for t in all_tournaments if t.is_visible_to(request.user)]
    my_invites = []
    if request.user.is_authenticated:
        profile = getattr(request.user, 'player_profile', None)
        if profile:
            my_invites = TournamentInvite.objects.select_related('tournament', 'invited_by').filter(invitee=profile, status='pending')
    return render(request, 'core/tournament_list.html', {'tournaments': tournaments, 'my_invites': my_invites})


def tournament_detail(request, slug):
    tournament = get_object_or_404(Tournament, slug=slug)
    if not tournament.is_visible_to(request.user):
        messages.error(request, 'This tournament is private.')
        return redirect('tournament_list')
    groups = tournament.groups.prefetch_related('memberships__participant__player__user', 'matches__home_player__user', 'matches__away_player__user')
    group_tables = tournament_logic.group_tables(tournament)
    knockout = tournament.matches.select_related('home_player__user', 'away_player__user', 'winner__user').exclude(stage='group')
    selected_participants = tournament.participants.select_related('player__user').filter(status='selected')
    reserve_participants = tournament.participants.select_related('player__user').filter(status='reserve')
    can_manage = tournament.can_manage(request.user)
    invite_form = TournamentInviteForm(tournament=tournament) if can_manage else None
    pending_invites = tournament.invites.select_related('invitee__user').filter(status='pending') if can_manage else []
    return render(request, 'core/tournament_detail.html', {
        'tournament': tournament,
        'groups': groups,
        'group_tables': group_tables,
        'knockout': knockout,
        'selected_participants': selected_participants,
        'reserve_participants': reserve_participants,
        'next_stage_format': next_stage_format(tournament.groups.count()),
        'can_manage': can_manage,
        'invite_form': invite_form,
        'pending_invites': pending_invites,
    })


@staff_required
def create_tournament(request):
    form = TournamentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        tournament = form.save(commit=False)
        tournament.visibility = 'public'
        tournament.created_by = request.user
        tournament.save()
        messages.success(request, 'Tournament created successfully.')
        return redirect('tournament_detail', slug=tournament.slug)
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Create tournament', 'form': form})


@login_required
def create_private_tournament(request):
    form = PrivateTournamentForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        tournament = form.save(commit=False)
        tournament.visibility = 'private'
        tournament.created_by = request.user
        tournament.status = 'draft'
        tournament.save()
        TournamentParticipant.objects.create(tournament=tournament, player=request.user.player_profile, seed=1, status='selected')
        messages.success(request, 'Private tournament created. Invite your friends to join.')
        return redirect('tournament_detail', slug=tournament.slug)
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Create private tournament', 'form': form})


@login_required
@require_POST
def invite_to_tournament(request, slug):
    tournament = get_object_or_404(Tournament, slug=slug)
    if not tournament.can_manage(request.user):
        messages.error(request, 'You do not have permission to invite players to this tournament.')
        return redirect('tournament_detail', slug=slug)
    form = TournamentInviteForm(request.POST, tournament=tournament)
    if form.is_valid():
        profile = form.cleaned_data['profile']
        invite = TournamentInvite.objects.create(tournament=tournament, invited_by=request.user, invitee=profile)
        create_notification(
            profile.user,
            'Tournament invite',
            f'{request.user.username} invited you to join "{tournament.name}".',
            'tournament_invite',
            '/tournaments/',
        )
        messages.success(request, f'Invite sent to {profile.user.username}.')
    else:
        add_form_error_messages(request, form)
    return redirect('tournament_detail', slug=slug)


@login_required
@require_POST
def respond_tournament_invite(request, pk, action):
    profile = request.user.player_profile
    invite = get_object_or_404(TournamentInvite, pk=pk, invitee=profile, status='pending')
    if action == 'accept':
        invite.status = 'accepted'
        invite.save(update_fields=['status', 'updated_at'])
        seed = invite.tournament.participants.count() + 1
        TournamentParticipant.objects.get_or_create(tournament=invite.tournament, player=profile, defaults={'seed': seed, 'status': 'selected'})
        if invite.invited_by:
            create_notification(invite.invited_by, 'Invite accepted', f'{request.user.username} joined "{invite.tournament.name}".', 'tournament_invite', invite.tournament.get_absolute_url())
        messages.success(request, f'You joined {invite.tournament.name}.')
        tournament = invite.tournament
        if (not tournament.groups_generated
                and tournament.participants.filter(status='selected').count() >= tournament.max_participants):
            if run_structure_generation(request, tournament):
                messages.info(request, f'"{tournament.name}" is full — the draw and fixtures were generated automatically.')
    elif action == 'decline':
        invite.status = 'declined'
        invite.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Invite declined.')
    return redirect('tournament_list')


@tournament_manager_required
def add_tournament_participant(request, slug):
    tournament = get_object_or_404(Tournament, slug=slug)
    if tournament.participants.count() >= tournament.max_participants:
        messages.error(request, 'Tournament is full.')
        return redirect('tournament_detail', slug=slug)
    form = TournamentParticipantForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        participant = form.save(commit=False)
        participant.tournament = tournament
        participant.seed = tournament.participants.count() + 1
        participant.save()
        messages.success(request, 'Created successfully.')
        if (not tournament.groups_generated
                and tournament.participants.filter(status='selected').count() >= tournament.max_participants):
            if run_structure_generation(request, tournament):
                messages.info(request, f'"{tournament.name}" is full — the draw and fixtures were generated automatically.')
        return redirect('tournament_detail', slug=slug)
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': f'Add participant to {tournament.name}', 'form': form})


def next_stage_format(group_count):
    if group_count == 8:
        return 'Round of 16'
    if group_count == 4:
        return 'Quarter-finals'
    if group_count == 2:
        return 'Semi-finals'
    if group_count == 1:
        return 'League table decides the champion'
    if group_count:
        return 'Knockout completed with best third-placed players'
    return 'Groups not generated yet'


def run_structure_generation(request, tournament):
    try:
        selected_count, reserve_count, group_count = tournament_logic.generate_structure(tournament)
    except ValueError as exc:
        messages.error(request, str(exc))
        return False
    if reserve_count:
        messages.info(request, f'{selected_count} players selected, {reserve_count} added to reserves.')
    if group_count:
        messages.success(request, f'{selected_count} players drawn into {group_count} group(s); fixtures generated ({"home & away" if tournament.group_legs == 2 else "single round"}).')
    else:
        messages.success(request, f'Knockout bracket generated for {selected_count} players.')
    for participant in tournament.participants.select_related('player__user').filter(status='selected'):
        create_notification(
            participant.player.user,
            'Tournament draw completed',
            f'The draw for "{tournament.name}" is done. Check your group and fixtures.',
            'tournament_invite',
            tournament.get_absolute_url(),
        )
    return True


@tournament_manager_required
@require_POST
def generate_tournament_groups(request, slug):
    tournament = get_object_or_404(Tournament, slug=slug)
    if tournament.groups_generated:
        messages.error(request, 'Groups already generated for this tournament.')
        return redirect('tournament_detail', slug=slug)
    run_structure_generation(request, tournament)
    return redirect('tournament_detail', slug=slug)


@tournament_manager_required
@require_POST
def generate_group_fixtures(request, slug):
    tournament = get_object_or_404(Tournament, slug=slug, groups_generated=True)
    if tournament.group_fixtures_generated:
        messages.error(request, 'Group fixtures already generated.')
        return redirect('tournament_detail', slug=slug)
    tournament_logic.create_group_fixtures(tournament)
    tournament.group_fixtures_generated = True
    tournament.status = 'group_stage'
    tournament.save(update_fields=['group_fixtures_generated', 'status', 'updated_at'])
    messages.success(request, 'Group fixtures generated.')
    return redirect('tournament_detail', slug=slug)


@tournament_manager_required
@require_POST
def generate_knockout(request, slug):
    tournament = get_object_or_404(Tournament, slug=slug, group_fixtures_generated=True)
    if tournament.knockout_generated:
        messages.error(request, 'Knockout stage already generated.')
        return redirect('tournament_detail', slug=slug)
    if tournament.matches.filter(stage='group').exclude(status='played').exists():
        messages.error(request, 'All group matches must be played before knockout generation.')
        return redirect('tournament_detail', slug=slug)
    try:
        stage, pair_count = tournament_logic.generate_knockout_bracket(tournament)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('tournament_detail', slug=slug)
    messages.success(request, f'Knockout stage generated: {pair_count} {stage.replace("_", " ")} matches. Group rivals can only meet again in the final.')
    return redirect('tournament_detail', slug=slug)


@login_required
def update_tournament_match(request, pk):
    match = get_object_or_404(TournamentMatch.objects.select_related('tournament'), pk=pk)
    if not match.tournament.can_manage(request.user):
        messages.error(request, 'You do not have permission to manage this tournament.')
        return redirect('tournament_detail', slug=match.tournament.slug)
    form = TournamentMatchScoreForm(request.POST or None, instance=match)
    if request.method == 'POST' and form.is_valid():
        match = form.save(commit=False)
        if match.status == 'played':
            if match.stage == 'group':
                if match.home_score > match.away_score:
                    match.winner = match.home_player
                elif match.away_score > match.home_score:
                    match.winner = match.away_player
                else:
                    match.winner = None
            else:
                match.winner = tournament_logic.resolve_winner(match)
        match.save()
        tournament_logic.advance_knockout(match.tournament)
        tournament_logic.maybe_complete_league(match.tournament)
        messages.success(request, 'Score saved successfully.')
        return redirect('tournament_detail', slug=match.tournament.slug)
    if request.method == 'POST':
        add_form_error_messages(request, form)
    return render(request, 'core/form_page.html', {'title': 'Update tournament match', 'form': form})
