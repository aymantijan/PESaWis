from django.contrib import admin

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
    NewsLike,
    NewsPost,
    NewsReaction,
    Notification,
    NotificationPreference,
    PlayerProfile,
    Season,
    Tournament,
    TournamentGroup,
    TournamentGroupMembership,
    TournamentMatch,
    TournamentParticipant,
)


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'konami_id', 'city', 'is_public', 'created_at')
    search_fields = ('user__username', 'full_name', 'konami_id', 'city')
    list_filter = ('is_public',)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'status', 'visibility', 'organizer')
    list_filter = ('status', 'visibility')
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ('name', 'league', 'status', 'start_date', 'end_date')
    list_filter = ('status', 'league')
    search_fields = ('name', 'league__name')


@admin.register(Division)
class DivisionAdmin(admin.ModelAdmin):
    list_display = ('name', 'season', 'order')
    list_filter = ('season__league', 'season')
    search_fields = ('name', 'season__name')


@admin.register(DivisionMembership)
class DivisionMembershipAdmin(admin.ModelAdmin):
    list_display = ('player', 'division', 'is_active')
    list_filter = ('is_active', 'division__season__league')
    search_fields = ('player__user__username', 'division__name')


@admin.register(LeagueMembership)
class LeagueMembershipAdmin(admin.ModelAdmin):
    list_display = ('player', 'league', 'role', 'status')
    list_filter = ('role', 'status', 'league')
    search_fields = ('player__user__username', 'league__name')


@admin.register(LeagueJoinRequest)
class LeagueJoinRequestAdmin(admin.ModelAdmin):
    list_display = ('player', 'league', 'status', 'created_at')
    list_filter = ('status', 'league')
    search_fields = ('player__user__username', 'league__name')


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ('home_player', 'away_player', 'match_type', 'status', 'home_score', 'away_score', 'scheduled_at')
    list_filter = ('match_type', 'status', 'league', 'division')
    search_fields = ('home_player__user__username', 'away_player__user__username')


@admin.register(FriendlyMatchRequest)
class FriendlyMatchRequestAdmin(admin.ModelAdmin):
    list_display = ('requester', 'opponent', 'status', 'proposed_at')
    list_filter = ('status',)
    search_fields = ('requester__user__username', 'opponent__user__username')


class NewsCommentInline(admin.TabularInline):
    model = NewsComment
    extra = 0


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ('author', 'is_pinned', 'photo', 'created_at')
    list_filter = ('is_pinned',)
    search_fields = ('author__username', 'content')
    inlines = [NewsCommentInline]


admin.site.register(NewsLike)
admin.site.register(NewsReaction)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'enabled', 'friendly_requests', 'match_updates', 'comments', 'system_updates')
    list_filter = ('enabled', 'friendly_requests', 'match_updates', 'comments', 'system_updates')
    search_fields = ('user__username',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('user__username', 'title', 'message')


class TournamentParticipantInline(admin.TabularInline):
    model = TournamentParticipant
    fields = ('player', 'seed', 'status')
    extra = 0


class TournamentGroupInline(admin.TabularInline):
    model = TournamentGroup
    extra = 0


@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'format', 'group_legs', 'visibility', 'champion', 'groups_generated', 'knockout_generated')
    list_filter = ('status', 'format', 'visibility')
    search_fields = ('name', 'slug')
    inlines = [TournamentParticipantInline, TournamentGroupInline]


@admin.register(LiveStream)
class LiveStreamAdmin(admin.ModelAdmin):
    list_display = ('title', 'streamer', 'status', 'created_at', 'ended_at')
    list_filter = ('status',)
    search_fields = ('title', 'streamer__username')


@admin.register(TournamentGroup)
class TournamentGroupAdmin(admin.ModelAdmin):
    list_display = ('tournament', 'name')


@admin.register(TournamentGroupMembership)
class TournamentGroupMembershipAdmin(admin.ModelAdmin):
    list_display = ('group', 'participant')


@admin.register(TournamentMatch)
class TournamentMatchAdmin(admin.ModelAdmin):
    list_display = ('tournament', 'stage', 'group', 'home_player', 'away_player', 'status', 'home_score', 'away_score', 'winner')
    list_filter = ('stage', 'status', 'tournament')


@admin.register(TournamentParticipant)
class TournamentParticipantAdmin(admin.ModelAdmin):
    list_display = ('tournament', 'player', 'seed', 'status')
    list_filter = ('status', 'tournament')
    search_fields = ('player__user__username', 'tournament__name')
