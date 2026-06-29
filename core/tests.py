from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import (
    Division,
    DivisionMembership,
    League,
    Match,
    NewsComment,
    NewsPost,
    NewsReaction,
    Notification,
    NotificationPreference,
    PlayerProfile,
    Season,
    Tournament,
    TournamentGroup,
    TournamentMatch,
    TournamentParticipant,
)


def make_user(username, konami_id):
    user = User.objects.create_user(username=username, password='StrongPass12345!')
    profile = user.player_profile
    profile.konami_id = konami_id
    profile.full_name = username.title()
    profile.save()
    return user


class AccountFeedLeagueTests(TestCase):
    def test_signup_creates_user_and_profile_without_email(self):
        response = self.client.post(reverse('signup'), {
            'username': 'newplayer',
            'full_name': 'New Player',
            'konami_id': 'KONAMI-100',
            'password1': 'StrongPass12345!',
            'password2': 'StrongPass12345!',
        })
        self.assertRedirects(response, reverse('dashboard'))
        user = User.objects.get(username='newplayer')
        self.assertEqual(user.email, '')
        self.assertEqual(user.player_profile.konami_id, 'KONAMI-100')
        self.assertEqual(user.player_profile.full_name, 'New Player')

    def test_feed_post_photo_comment_and_single_active_reaction(self):
        user = make_user('poster', 'KONAMI-101')
        self.client.login(username='poster', password='StrongPass12345!')
        upload = SimpleUploadedFile('goal.webp', b'fake image bytes', content_type='image/webp')
        response = self.client.post(reverse('news_feed'), {'content': 'Nice match', 'photo': upload})
        self.assertRedirects(response, reverse('news_feed'))
        post = NewsPost.objects.get()
        self.assertTrue(post.photo.name.endswith('.webp'))

        self.client.post(reverse('react_post', args=[post.pk, 'like']))
        self.assertEqual(NewsReaction.objects.get(post=post, user=user).reaction, 'like')
        self.client.post(reverse('react_post', args=[post.pk, 'dislike']))
        self.assertEqual(NewsReaction.objects.get(post=post, user=user).reaction, 'dislike')
        self.client.post(reverse('react_post', args=[post.pk, 'dislike']))
        self.assertFalse(NewsReaction.objects.filter(post=post, user=user).exists())

        self.client.post(reverse('add_comment', args=[post.pk]), {'content': 'Well played'})
        self.assertEqual(NewsComment.objects.get(post=post).content, 'Well played')

    def test_feed_author_can_edit_and_delete_own_post(self):
        user = make_user('postowner', 'KONAMI-102')
        self.client.login(username='postowner', password='StrongPass12345!')
        post = NewsPost.objects.create(author=user, content='Original post')
        NewsComment.objects.create(post=post, author=user, content='Comment')
        NewsReaction.objects.create(post=post, user=user, reaction='like')

        response = self.client.post(reverse('edit_post', args=[post.pk]), {'content': 'Updated post'})
        self.assertRedirects(response, reverse('news_feed'))
        post.refresh_from_db()
        self.assertEqual(post.content, 'Updated post')

        response = self.client.post(reverse('delete_post', args=[post.pk]))
        self.assertRedirects(response, reverse('news_feed'))
        self.assertFalse(NewsPost.objects.filter(pk=post.pk).exists())
        self.assertFalse(NewsComment.objects.filter(post_id=post.pk).exists())
        self.assertFalse(NewsReaction.objects.filter(post_id=post.pk).exists())

    def test_other_user_cannot_edit_or_delete_post(self):
        owner = make_user('realowner', 'KONAMI-103')
        other = make_user('otheruser', 'KONAMI-104')
        post = NewsPost.objects.create(author=owner, content='Owner post')
        self.client.login(username='otheruser', password='StrongPass12345!')

        response = self.client.post(reverse('edit_post', args=[post.pk]), {'content': 'Hijacked'})
        self.assertRedirects(response, reverse('news_feed'))
        post.refresh_from_db()
        self.assertEqual(post.content, 'Owner post')

        response = self.client.post(reverse('delete_post', args=[post.pk]))
        self.assertRedirects(response, reverse('news_feed'))
        self.assertTrue(NewsPost.objects.filter(pk=post.pk).exists())

    def test_comment_author_can_edit_and_delete_own_comment(self):
        user = make_user('commenter', 'KONAMI-105')
        post = NewsPost.objects.create(author=user, content='Post')
        comment = NewsComment.objects.create(post=post, author=user, content='Original comment')
        self.client.login(username='commenter', password='StrongPass12345!')

        response = self.client.post(reverse('edit_comment', args=[comment.pk]), {'content': 'Updated comment'})
        self.assertRedirects(response, reverse('news_feed'))
        comment.refresh_from_db()
        self.assertEqual(comment.content, 'Updated comment')

        response = self.client.post(reverse('delete_comment', args=[comment.pk]))
        self.assertRedirects(response, reverse('news_feed'))
        self.assertFalse(NewsComment.objects.filter(pk=comment.pk).exists())

    def test_other_user_cannot_edit_or_delete_comment(self):
        owner = make_user('commentowner', 'KONAMI-106')
        other = make_user('commentother', 'KONAMI-107')
        post = NewsPost.objects.create(author=owner, content='Post')
        comment = NewsComment.objects.create(post=post, author=owner, content='Owner comment')
        self.client.login(username='commentother', password='StrongPass12345!')

        response = self.client.post(reverse('edit_comment', args=[comment.pk]), {'content': 'Changed'})
        self.assertRedirects(response, reverse('news_feed'))
        comment.refresh_from_db()
        self.assertEqual(comment.content, 'Owner comment')

        response = self.client.post(reverse('delete_comment', args=[comment.pk]))
        self.assertRedirects(response, reverse('news_feed'))
        self.assertTrue(NewsComment.objects.filter(pk=comment.pk).exists())

    def test_rules_public_staff_protected_and_profile_photo_validation(self):
        response = self.client.get(reverse('rules'))
        self.assertContains(response, 'Win = 3 points')
        self.assertNotContains(response, 'Victoire = 3 points')
        self.assertNotContains(response, 'الفوز = 3 نقاط')

        response = self.client.get(reverse('rules') + '?lang=en')
        self.assertContains(response, 'General Principles')
        self.assertNotContains(response, 'Principes généraux')

        response = self.client.get(reverse('rules') + '?lang=fr')
        self.assertContains(response, 'Victoire = 3 points')
        self.assertContains(response, 'Principes généraux')
        self.assertNotContains(response, 'Win = 3 points')

        response = self.client.get(reverse('rules') + '?lang=ar')
        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, 'الفوز = 3 نقاط')
        self.assertNotContains(response, 'Win = 3 points')

        response = self.client.get(reverse('rules') + '?lang=wrong')
        self.assertContains(response, 'Win = 3 points')
        self.assertNotContains(response, 'Victoire = 3 points')

        response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(response.status_code, 302)

        user = make_user('photo', 'KONAMI-150')
        self.client.login(username='photo', password='StrongPass12345!')
        valid_photo = SimpleUploadedFile('avatar.png', b'fake image bytes', content_type='image/png')
        response = self.client.post(reverse('edit_profile'), {
            'full_name': 'Photo User',
            'konami_id': 'KONAMI-150',
            'city': '',
            'main_play_style': '',
            'favorite_formation': '',
            'bio': '',
            'is_public': 'on',
            'profile_photo': valid_photo,
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(User.objects.get(username='photo').player_profile.profile_photo.name.endswith('.png'))

        bad_photo = SimpleUploadedFile('avatar.exe', b'bad', content_type='application/octet-stream')
        response = self.client.post(reverse('edit_profile'), {
            'full_name': 'Photo User',
            'konami_id': 'KONAMI-150',
            'city': '',
            'main_play_style': '',
            'favorite_formation': '',
            'bio': '',
            'is_public': 'on',
            'profile_photo': bad_photo,
        })
        self.assertContains(response, 'Only JPG, PNG or WEBP images are allowed.')

    def test_notifications_preferences_friendly_request_and_comment(self):
        author = make_user('author', 'KONAMI-160')
        opponent = make_user('opponent', 'KONAMI-161')
        NotificationPreference.objects.update_or_create(user=opponent, defaults={'enabled': True})
        NotificationPreference.objects.update_or_create(user=author, defaults={'enabled': True})

        self.client.login(username='author', password='StrongPass12345!')
        response = self.client.post(reverse('request_friendly_match', args=['opponent']), {'message': 'Play?'})
        self.assertRedirects(response, reverse('player_detail', args=['opponent']))
        self.assertTrue(Notification.objects.filter(user=opponent, notification_type='friendly_request').exists())

        post = NewsPost.objects.create(author=author, content='My post')
        self.client.logout()
        self.client.login(username='opponent', password='StrongPass12345!')
        self.client.post(reverse('add_comment', args=[post.pk]), {'content': 'Nice'})
        self.assertTrue(Notification.objects.filter(user=author, notification_type='comment').exists())

        response = self.client.get(reverse('notifications'))
        self.assertContains(response, 'Notifications')
        notification = Notification.objects.filter(user=author).first()
        self.client.logout()
        self.client.login(username='author', password='StrongPass12345!')
        response = self.client.post(reverse('mark_notification_read', args=[notification.pk]))
        self.assertRedirects(response, reverse('notifications'))

    def test_staff_can_generate_round_robin_calendar_once(self):
        staff = make_user('staff', 'KONAMI-200')
        staff.is_staff = True
        staff.save()
        league = League.objects.create(name='League')
        season = Season.objects.create(league=league, name='Season', status='active')
        division = Division.objects.create(season=season, name='ELITE', order=1)
        for index in range(4):
            user = make_user(f'p{index}', f'KONAMI-20{index + 1}')
            DivisionMembership.objects.create(division=division, player=user.player_profile)
        self.client.login(username='staff', password='StrongPass12345!')
        response = self.client.post(reverse('create_calendar'), {'division': division.pk})
        self.assertRedirects(response, reverse('calendar'))
        self.assertEqual(Match.objects.filter(division=division, match_type='official').count(), 6)
        response = self.client.post(reverse('create_calendar'), {'division': division.pk})
        self.assertRedirects(response, reverse('calendar'))
        self.assertEqual(Match.objects.filter(division=division, match_type='official').count(), 6)


class TournamentTests(TestCase):
    def setUp(self):
        self.staff = make_user('manager', 'KONAMI-300')
        self.staff.is_staff = True
        self.staff.save()
        self.staff.player_profile.is_public = False
        self.staff.player_profile.save()
        self.tournament = Tournament.objects.create(name='Cup')
        self.players = [make_user(f'tp{i}', f'KONAMI-30{i + 1}').player_profile for i in range(8)]
        for player in self.players:
            TournamentParticipant.objects.create(tournament=self.tournament, player=player)
        self.client.login(username='manager', password='StrongPass12345!')

    def test_tournament_group_fixtures_qualification_and_knockout(self):
        self.client.post(reverse('generate_tournament_groups', args=[self.tournament.slug]))
        self.assertEqual(TournamentGroup.objects.filter(tournament=self.tournament).count(), 2)
        self.client.post(reverse('generate_group_fixtures', args=[self.tournament.slug]))
        self.assertEqual(TournamentMatch.objects.filter(tournament=self.tournament, stage='group').count(), 12)

        for match in TournamentMatch.objects.filter(tournament=self.tournament, stage='group'):
            match.home_score = 1
            match.away_score = 0
            match.winner = match.home_player
            match.status = 'played'
            match.save()

        self.client.post(reverse('generate_knockout', args=[self.tournament.slug]))
        self.assertEqual(TournamentMatch.objects.filter(tournament=self.tournament).exclude(stage='group').count(), 2)

    def test_auto_select_uses_performance_and_creates_reserves(self):
        PlayerProfile.objects.update(is_public=False)
        tournament = Tournament.objects.create(name='Auto Cup')
        players = [make_user(f'a{i}', f'KONAMI-40{i}').player_profile for i in range(9)]
        winner = make_user('zzwinner', 'KONAMI-499').player_profile
        Match.objects.create(
            match_type='official',
            home_player=winner,
            away_player=players[-1],
            status='played',
            home_score=3,
            away_score=0,
        )

        self.client.post(reverse('generate_tournament_groups', args=[tournament.slug]))
        self.assertEqual(TournamentParticipant.objects.filter(tournament=tournament, status='selected').count(), 8)
        self.assertEqual(TournamentParticipant.objects.filter(tournament=tournament, status='reserve').count(), 2)
        self.assertTrue(TournamentParticipant.objects.filter(tournament=tournament, player=winner, status='selected').exists())
        self.assertEqual(TournamentGroup.objects.filter(tournament=tournament).count(), 2)
        self.assertEqual(TournamentMatch.objects.filter(tournament=tournament, stage='group').count(), 12)

    def test_auto_select_supports_28_player_group_format(self):
        PlayerProfile.objects.update(is_public=False)
        tournament = Tournament.objects.create(name='Twenty Eight Cup')
        for index in range(30):
            make_user(f'p28_{index:02d}', f'KONAMI-50{index:02d}')

        self.client.post(reverse('generate_tournament_groups', args=[tournament.slug]))
        self.assertEqual(TournamentParticipant.objects.filter(tournament=tournament, status='selected').count(), 28)
        self.assertEqual(TournamentParticipant.objects.filter(tournament=tournament, status='reserve').count(), 2)
        self.assertEqual(TournamentGroup.objects.filter(tournament=tournament).count(), 7)
        self.assertEqual(TournamentMatch.objects.filter(tournament=tournament, stage='group').count(), 42)
