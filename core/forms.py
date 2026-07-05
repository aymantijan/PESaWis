from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import (
    Division,
    DivisionMembership,
    FriendlyMatchRequest,
    League,
    Match,
    NewsComment,
    NewsPost,
    NotificationPreference,
    PlayerProfile,
    Season,
    Tournament,
    TournamentInvite,
    TournamentMatch,
    TournamentParticipant,
)


REQUIRED_ERROR = {'required': 'This field is required.'}


class LoginForm(AuthenticationForm):
    error_messages = {
        'invalid_login': 'Invalid username or password.',
        'inactive': 'This account is inactive.',
    }


class SignupForm(UserCreationForm):
    konami_id = forms.CharField(max_length=64, required=True, label='Konami ID', error_messages=REQUIRED_ERROR)
    full_name = forms.CharField(max_length=180, required=True, label='Full name', error_messages=REQUIRED_ERROR)
    error_messages = {
        'password_mismatch': 'The two password fields did not match.',
    }

    class Meta:
        model = User
        fields = ('username', 'konami_id', 'full_name', 'password1', 'password2')
        error_messages = {
            'username': {
                'required': 'This field is required.',
                'unique': 'This username already exists.',
            },
        }

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username already exists.')
        return username

    def clean_konami_id(self):
        konami_id = self.cleaned_data['konami_id'].strip()
        if PlayerProfile.objects.filter(konami_id__iexact=konami_id).exists():
            raise forms.ValidationError('This Konami ID already exists.')
        return konami_id

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data['full_name'].strip()
        parts = full_name.split(' ', 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ''
        if commit:
            user.save()
            profile = user.player_profile
            profile.konami_id = self.cleaned_data['konami_id'].strip()
            profile.full_name = full_name
            profile.save()
        return user


class PlayerProfileForm(forms.ModelForm):
    class Meta:
        model = PlayerProfile
        fields = ('full_name', 'konami_id', 'profile_photo', 'city', 'main_play_style', 'favorite_formation', 'bio', 'is_public')
        widgets = {
            'profile_photo': forms.FileInput(attrs={'accept': '.jpg,.jpeg,.png,.webp'}),
            'bio': forms.Textarea(attrs={'rows': 4}),
        }
        error_messages = {
            'konami_id': {'unique': 'This Konami ID already exists.', 'required': 'This field is required.'},
        }


class LeagueForm(forms.ModelForm):
    class Meta:
        model = League
        fields = ('name', 'description', 'status', 'visibility')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class SeasonForm(forms.ModelForm):
    class Meta:
        model = Season
        fields = ('league', 'name', 'status', 'start_date', 'end_date')
        error_messages = {
            'league': REQUIRED_ERROR,
            'name': REQUIRED_ERROR,
            'status': REQUIRED_ERROR,
        }
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('start_date')
        end = cleaned.get('end_date')
        if start and end and end < start:
            raise forms.ValidationError('End date must be after start date.')
        return cleaned


class DivisionForm(forms.ModelForm):
    class Meta:
        model = Division
        fields = ('season', 'name', 'order')
        error_messages = {
            'season': REQUIRED_ERROR,
            'name': REQUIRED_ERROR,
            'order': REQUIRED_ERROR,
        }


class DivisionMembershipForm(forms.ModelForm):
    class Meta:
        model = DivisionMembership
        fields = ('division', 'player', 'is_active')
        error_messages = {
            'division': REQUIRED_ERROR,
            'player': REQUIRED_ERROR,
        }


class MatchForm(forms.ModelForm):
    class Meta:
        model = Match
        fields = (
            'match_type', 'league', 'season', 'division', 'home_player', 'away_player',
            'round_number', 'scheduled_at', 'status', 'home_score', 'away_score', 'notes'
        )
        widgets = {
            'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean(self):
        cleaned = super().clean()
        home = cleaned.get('home_player')
        away = cleaned.get('away_player')
        status = cleaned.get('status')
        hs = cleaned.get('home_score')
        as_ = cleaned.get('away_score')
        if home and away and home == away:
            raise forms.ValidationError('A player cannot play against himself.')
        if status == 'played' and (hs is None or as_ is None):
            raise forms.ValidationError('Invalid score.')
        return cleaned


class NewsPostForm(forms.ModelForm):
    tagged_users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(player_profile__isnull=False).order_by('username'),
        required=False,
        label='Tag players',
        widget=forms.SelectMultiple(attrs={'class': 'tag-select', 'data-placeholder': 'Tag players in this post'}),
    )

    class Meta:
        model = NewsPost
        fields = ('content', 'photo', 'tagged_users')
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': "Share league news, results or announcements... use @ to tag a player"}),
            'photo': forms.FileInput(attrs={'accept': '.jpg,.jpeg,.png,.webp'}),
        }
        error_messages = {'content': REQUIRED_ERROR}

    def save(self, commit=True):
        post = super().save(commit=commit)
        if commit:
            post.tagged_users.set(self.cleaned_data.get('tagged_users', []))
        return post


class NewsCommentForm(forms.ModelForm):
    tagged_users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(player_profile__isnull=False).order_by('username'),
        required=False,
        label='Tag players',
        widget=forms.SelectMultiple(attrs={'class': 'tag-select', 'data-placeholder': 'Tag someone'}),
    )

    class Meta:
        model = NewsComment
        fields = ('content', 'tagged_users')
        widgets = {'content': forms.TextInput(attrs={'placeholder': 'Write a comment... use @ to tag a player'})}
        error_messages = {'content': REQUIRED_ERROR}

    def save(self, commit=True):
        comment = super().save(commit=commit)
        if commit:
            comment.tagged_users.set(self.cleaned_data.get('tagged_users', []))
        return comment


class FriendlyMatchRequestForm(forms.ModelForm):
    class Meta:
        model = FriendlyMatchRequest
        fields = ('proposed_at', 'message')
        widgets = {
            'proposed_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Optional message'}),
        }


class NotificationPreferenceForm(forms.ModelForm):
    class Meta:
        model = NotificationPreference
        fields = ('enabled', 'friendly_requests', 'match_updates', 'comments', 'tags', 'tournament_invites', 'system_updates')
        labels = {
            'enabled': 'Enable notifications',
            'friendly_requests': 'Friendly requests',
            'match_updates': 'Match updates',
            'comments': 'Comments',
            'tags': 'Tags & mentions',
            'tournament_invites': 'Tournament invites',
            'system_updates': 'System updates',
        }


class CalendarGenerationForm(forms.Form):
    division = forms.ModelChoiceField(queryset=Division.objects.select_related('season__league').all())
    double_round_robin = forms.BooleanField(required=False, initial=False, label='Double round-robin')


class TournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ('name', 'status', 'max_participants')
        error_messages = {
            'name': REQUIRED_ERROR,
            'status': REQUIRED_ERROR,
            'max_participants': REQUIRED_ERROR,
        }


class TournamentParticipantForm(forms.ModelForm):
    class Meta:
        model = TournamentParticipant
        fields = ('player',)


class PrivateTournamentForm(forms.ModelForm):
    class Meta:
        model = Tournament
        fields = ('name', 'max_participants')
        error_messages = {
            'name': REQUIRED_ERROR,
            'max_participants': REQUIRED_ERROR,
        }


class TournamentInviteForm(forms.Form):
    username = forms.CharField(max_length=150, label='Player username', error_messages=REQUIRED_ERROR)

    def __init__(self, *args, tournament=None, **kwargs):
        self.tournament = tournament
        super().__init__(*args, **kwargs)

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        try:
            profile = PlayerProfile.objects.select_related('user').get(user__username__iexact=username)
        except PlayerProfile.DoesNotExist:
            raise forms.ValidationError('No player with this username was found.')
        if self.tournament and self.tournament.participants.filter(player=profile).exists():
            raise forms.ValidationError('This player is already in the tournament.')
        if self.tournament and self.tournament.invites.filter(invitee=profile, status='pending').exists():
            raise forms.ValidationError('This player already has a pending invite.')
        self.cleaned_data['profile'] = profile
        return username


class TournamentMatchScoreForm(forms.ModelForm):
    class Meta:
        model = TournamentMatch
        fields = ('home_score', 'away_score', 'winner', 'status')

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('status')
        home_score = cleaned.get('home_score')
        away_score = cleaned.get('away_score')
        winner = cleaned.get('winner')
        if status == 'played' and (home_score is None or away_score is None):
            raise forms.ValidationError('Invalid score.')
        if self.instance.stage != 'group' and status == 'played':
            valid_winners = {self.instance.home_player_id, self.instance.away_player_id}
            if winner is None:
                raise forms.ValidationError('Choose a winner for knockout matches.')
            if winner.id not in valid_winners:
                raise forms.ValidationError('Winner must be one of the match players.')
            if home_score == away_score and winner is None:
                raise forms.ValidationError('Choose a penalty/manual winner for a tied knockout match.')
        return cleaned
