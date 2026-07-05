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
    TournamentInvite,
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
        matches = Match.objects.filter(division=division, match_type='official')
        self.assertEqual(matches.count(), 6)
        # real football calendar: 4 players -> 3 rounds, everyone plays once per round
        rounds = {}
        for match in matches:
            rounds.setdefault(match.round_number, []).append(match)
        self.assertEqual(set(rounds), {1, 2, 3})
        for round_matches in rounds.values():
            players_in_round = [m.home_player_id for m in round_matches] + [m.away_player_id for m in round_matches]
            self.assertEqual(len(players_in_round), len(set(players_in_round)))
            self.assertEqual(len(round_matches), 2)
        response = self.client.post(reverse('create_calendar'), {'division': division.pk})
        self.assertRedirects(response, reverse('calendar'))
        self.assertEqual(Match.objects.filter(division=division, match_type='official').count(), 6)

    def test_double_round_robin_calendar_mirrors_legs(self):
        staff = make_user('staff2', 'KONAMI-210')
        staff.is_staff = True
        staff.save()
        league = League.objects.create(name='League 2')
        season = Season.objects.create(league=league, name='Season 2', status='active')
        division = Division.objects.create(season=season, name='D1', order=1)
        for index in range(4):
            user = make_user(f'dp{index}', f'KONAMI-21{index + 1}')
            DivisionMembership.objects.create(division=division, player=user.player_profile)
        self.client.login(username='staff2', password='StrongPass12345!')
        self.client.post(reverse('create_calendar'), {'division': division.pk, 'double_round_robin': 'on'})
        matches = list(Match.objects.filter(division=division, match_type='official'))
        self.assertEqual(len(matches), 12)
        self.assertEqual({m.round_number for m in matches}, set(range(1, 7)))
        first_leg = {(m.home_player_id, m.away_player_id) for m in matches if m.round_number <= 3}
        second_leg = {(m.home_player_id, m.away_player_id) for m in matches if m.round_number > 3}
        self.assertEqual({(a, h) for h, a in first_leg}, second_leg)


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

    def play_all_group_matches(self, tournament):
        """Home player always wins so group order follows seeding."""
        for match in TournamentMatch.objects.filter(tournament=tournament, stage='group'):
            match.home_score = 2
            match.away_score = 0
            match.winner = match.home_player
            match.status = 'played'
            match.save()

    def test_group_fixtures_are_home_and_away_round_robin(self):
        self.client.post(reverse('generate_tournament_groups', args=[self.tournament.slug]))
        self.assertEqual(TournamentGroup.objects.filter(tournament=self.tournament).count(), 2)
        group_matches = TournamentMatch.objects.filter(tournament=self.tournament, stage='group')
        # 2 groups of 4, home & away: 12 matches per group
        self.assertEqual(group_matches.count(), 24)
        for group in TournamentGroup.objects.filter(tournament=self.tournament):
            matches = list(group.matches.all())
            self.assertEqual(len(matches), 12)
            self.assertEqual({m.round_number for m in matches}, set(range(1, 7)))
            # every player plays exactly once per round
            for round_number in range(1, 7):
                ids = [m.home_player_id for m in matches if m.round_number == round_number]
                ids += [m.away_player_id for m in matches if m.round_number == round_number]
                self.assertEqual(len(ids), 4)
                self.assertEqual(len(set(ids)), 4)
            # each pairing appears once per venue
            pairs = [(m.home_player_id, m.away_player_id) for m in matches]
            self.assertEqual(len(pairs), len(set(pairs)))

    def test_knockout_uses_fifa_cross_pairings_then_final_and_third_place(self):
        self.client.post(reverse('generate_tournament_groups', args=[self.tournament.slug]))
        self.play_all_group_matches(self.tournament)
        self.client.post(reverse('generate_knockout', args=[self.tournament.slug]))
        semis = list(TournamentMatch.objects.filter(tournament=self.tournament, stage='semi_final').order_by('bracket_slot'))
        self.assertEqual(len(semis), 2)
        # no semi-final between two players of the same group
        group_of = {}
        for group in TournamentGroup.objects.filter(tournament=self.tournament):
            for membership in group.memberships.all():
                group_of[membership.participant.player_id] = group.name
        for match in semis:
            self.assertNotEqual(group_of[match.home_player_id], group_of[match.away_player_id])

        for match in semis:
            match.home_score = 1
            match.away_score = 0
            match.status = 'played'
            match.winner = match.home_player
            match.save()
        self.client.post(reverse('update_tournament_match', args=[semis[0].pk]), {
            'home_score': 1, 'away_score': 0, 'status': 'played',
        })
        self.tournament.refresh_from_db()
        final = TournamentMatch.objects.filter(tournament=self.tournament, stage='final')
        third = TournamentMatch.objects.filter(tournament=self.tournament, stage='third_place')
        self.assertEqual(final.count(), 1)
        self.assertEqual(third.count(), 1)
        # third-place match is between the two semi-final losers
        losers = {semis[0].away_player_id, semis[1].away_player_id}
        third_match = third.get()
        self.assertEqual({third_match.home_player_id, third_match.away_player_id}, losers)

        final_match = final.get()
        response = self.client.post(reverse('update_tournament_match', args=[final_match.pk]), {
            'home_score': 2, 'away_score': 2, 'home_penalties': 5, 'away_penalties': 4, 'status': 'played',
        })
        self.tournament.refresh_from_db()
        final_match.refresh_from_db()
        self.assertEqual(final_match.winner_id, final_match.home_player_id)
        self.assertEqual(self.tournament.status, 'completed')
        self.assertEqual(self.tournament.champion_id, final_match.home_player_id)

    def test_tied_knockout_match_requires_decision(self):
        self.client.post(reverse('generate_tournament_groups', args=[self.tournament.slug]))
        self.play_all_group_matches(self.tournament)
        self.client.post(reverse('generate_knockout', args=[self.tournament.slug]))
        semi = TournamentMatch.objects.filter(tournament=self.tournament, stage='semi_final').first()
        self.client.post(reverse('update_tournament_match', args=[semi.pk]), {
            'home_score': 1, 'away_score': 1, 'status': 'played',
        })
        semi.refresh_from_db()
        self.assertEqual(semi.status, 'scheduled')  # rejected: no penalty score, no winner

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
        self.assertEqual(TournamentMatch.objects.filter(tournament=tournament, stage='group').count(), 24)

    def test_auto_select_supports_28_player_group_format(self):
        PlayerProfile.objects.update(is_public=False)
        tournament = Tournament.objects.create(name='Twenty Eight Cup', group_legs=1)
        for index in range(30):
            make_user(f'p28_{index:02d}', f'KONAMI-50{index:02d}')

        self.client.post(reverse('generate_tournament_groups', args=[tournament.slug]))
        self.assertEqual(TournamentParticipant.objects.filter(tournament=tournament, status='selected').count(), 28)
        self.assertEqual(TournamentParticipant.objects.filter(tournament=tournament, status='reserve').count(), 2)
        self.assertEqual(TournamentGroup.objects.filter(tournament=tournament).count(), 7)
        self.assertEqual(TournamentMatch.objects.filter(tournament=tournament, stage='group').count(), 42)

        # 7 groups qualify 14 players + 2 best thirds -> full round of 16
        self.play_all_group_matches(tournament)
        self.client.post(reverse('generate_knockout', args=[tournament.slug]))
        self.assertEqual(TournamentMatch.objects.filter(tournament=tournament, stage='round_of_16').count(), 8)

    def test_direct_knockout_format(self):
        tournament = Tournament.objects.create(name='KO Cup', format='knockout', created_by=self.staff)
        for player in self.players:
            TournamentParticipant.objects.create(tournament=tournament, player=player)
        self.client.post(reverse('generate_tournament_groups', args=[tournament.slug]))
        tournament.refresh_from_db()
        self.assertEqual(tournament.status, 'knockout')
        self.assertEqual(TournamentMatch.objects.filter(tournament=tournament, stage='quarter_final').count(), 4)
        self.assertEqual(TournamentGroup.objects.filter(tournament=tournament).count(), 0)

    def test_draw_autogenerates_when_tournament_full(self):
        organizer = make_user('organizer', 'KONAMI-600')
        joiners = [make_user(f'j{i}', f'KONAMI-61{i}') for i in range(3)]
        self.client.logout()
        self.client.login(username='organizer', password='StrongPass12345!')
        self.client.post(reverse('create_private_tournament'), {
            'name': 'Kas dial lma mini', 'max_participants': 4, 'format': 'groups_knockout', 'group_legs': 2,
        })
        tournament = Tournament.objects.get(name='Kas dial lma mini')
        for joiner in joiners:
            self.client.post(reverse('invite_to_tournament', args=[tournament.slug]), {'username': joiner.username})
        for joiner in joiners:
            self.client.logout()
            self.client.login(username=joiner.username, password='StrongPass12345!')
            invite = TournamentInvite.objects.get(tournament=tournament, invitee=joiner.player_profile)
            self.client.post(reverse('respond_tournament_invite', args=[invite.pk, 'accept']))
        tournament.refresh_from_db()
        self.assertTrue(tournament.groups_generated)
        self.assertEqual(tournament.status, 'group_stage')
        self.assertEqual(TournamentGroup.objects.filter(tournament=tournament).count(), 1)
        # 4 players home & away: 12 matches over 6 rounds
        self.assertEqual(TournamentMatch.objects.filter(tournament=tournament, stage='group').count(), 12)


class SeasonOutcomeTests(TestCase):
    def test_champion_promotion_and_relegation_follow_football_rules(self):
        staff = make_user('boss', 'KONAMI-700')
        staff.is_staff = True
        staff.save()
        league = League.objects.create(name='Ligue')
        season = Season.objects.create(league=league, name='S1', status='completed')
        div1 = Division.objects.create(season=season, name='Division 1', order=1)
        div2 = Division.objects.create(season=season, name='Division 2', order=2)
        d1_players = [make_user(f'd1p{i}', f'KONAMI-71{i}').player_profile for i in range(4)]
        d2_players = [make_user(f'd2p{i}', f'KONAMI-72{i}').player_profile for i in range(4)]
        for player in d1_players:
            DivisionMembership.objects.create(division=div1, player=player)
        for player in d2_players:
            DivisionMembership.objects.create(division=div2, player=player)

        def play(division, players):
            # players[0] beats everyone, players[1] beats the rest, etc.
            for i in range(len(players)):
                for j in range(i + 1, len(players)):
                    Match.objects.create(
                        match_type='official', league=league, season=season, division=division,
                        home_player=players[i], away_player=players[j],
                        status='played', home_score=2, away_score=0,
                    )
        play(div1, d1_players)
        play(div2, d2_players)

        from .utils import season_outcomes
        rows = season_outcomes(season)
        by_outcome = {}
        for row in rows:
            by_outcome.setdefault(row['outcome'], []).append(row)
        self.assertEqual(len(by_outcome.get('Champion', [])), 1)
        self.assertEqual(by_outcome['Champion'][0]['player'], d1_players[0])
        self.assertEqual(len(by_outcome.get('Promoted', [])), 2)
        self.assertEqual({r['player'] for r in by_outcome['Promoted']}, {d2_players[0], d2_players[1]})
        relegated = [r for r in rows if r['outcome'] == 'Relegated']
        self.assertEqual({r['player'] for r in relegated}, {d1_players[2], d1_players[3]})

        self.client.login(username='boss', password='StrongPass12345!')
        self.client.post(reverse('apply_promotion_relegation', args=[season.pk]))
        # promoted players are now active in div1 and inactive in div2
        self.assertTrue(DivisionMembership.objects.get(division=div1, player=d2_players[0]).is_active)
        self.assertFalse(DivisionMembership.objects.get(division=div2, player=d2_players[0]).is_active)
        self.assertTrue(DivisionMembership.objects.get(division=div2, player=d1_players[3]).is_active)
        self.assertFalse(DivisionMembership.objects.get(division=div1, player=d1_players[3]).is_active)


class LiveStreamTests(TestCase):
    def test_stream_lifecycle_and_signaling(self):
        broadcaster = make_user('caster', 'KONAMI-800')
        viewer = make_user('viewer', 'KONAMI-801')
        self.client.login(username='caster', password='StrongPass12345!')
        response = self.client.post(reverse('stream_start'), {'title': 'Derby live'})
        from .models import LiveStream, StreamSignal
        stream = LiveStream.objects.get(streamer=broadcaster)
        self.assertRedirects(response, reverse('stream_broadcast', args=[stream.pk]))
        self.assertEqual(stream.status, 'live')

        # viewer joins and signals the broadcaster
        self.client.logout()
        self.client.login(username='viewer', password='StrongPass12345!')
        response = self.client.post(
            reverse('stream_signal', args=[stream.pk]),
            data='{"kind": "join", "target": "broadcaster", "peer_id": "v-abc"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        # a viewer cannot impersonate the broadcaster
        response = self.client.post(
            reverse('stream_signal', args=[stream.pk]),
            data='{"kind": "offer", "target": "viewer", "peer_id": "v-abc"}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

        # broadcaster polls and receives the join
        self.client.logout()
        self.client.login(username='caster', password='StrongPass12345!')
        response = self.client.get(reverse('stream_poll', args=[stream.pk]) + '?role=broadcaster&after=0')
        data = response.json()
        self.assertEqual(data['status'], 'live')
        self.assertEqual(data['signals'][0]['kind'], 'join')

        # stop deletes all signaling data — nothing is stored
        response = self.client.post(reverse('stream_stop', args=[stream.pk]))
        self.assertRedirects(response, reverse('news_feed'))
        stream.refresh_from_db()
        self.assertEqual(stream.status, 'ended')
        self.assertEqual(StreamSignal.objects.filter(stream=stream).count(), 0)

    def test_feed_lists_live_streams(self):
        broadcaster = make_user('caster2', 'KONAMI-810')
        from .models import LiveStream
        LiveStream.objects.create(streamer=broadcaster, title='Kas dial lma final')
        response = self.client.get(reverse('news_feed'))
        self.assertContains(response, 'Kas dial lma final')
        self.assertContains(response, 'Live now')
