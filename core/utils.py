from collections import defaultdict

from .models import Match, PlayerProfile


def base_stats(player):
    return {
        'player': player,
        'played': 0,
        'wins': 0,
        'draws': 0,
        'losses': 0,
        'goals_for': 0,
        'goals_against': 0,
        'goal_diff': 0,
        'points': 0,
        'clean_sheets': 0,
    }


def compute_player_stats(matches, players=None):
    stats = {}
    if players is not None:
        for player in players:
            stats[player.id] = base_stats(player)

    for match in matches:
        if match.status != 'played' or not match.has_score:
            continue
        home = match.home_player
        away = match.away_player
        stats.setdefault(home.id, base_stats(home))
        stats.setdefault(away.id, base_stats(away))

        h = stats[home.id]
        a = stats[away.id]
        h['played'] += 1
        a['played'] += 1
        h['goals_for'] += match.home_score
        h['goals_against'] += match.away_score
        a['goals_for'] += match.away_score
        a['goals_against'] += match.home_score

        if match.away_score == 0:
            h['clean_sheets'] += 1
        if match.home_score == 0:
            a['clean_sheets'] += 1

        if match.home_score > match.away_score:
            h['wins'] += 1
            a['losses'] += 1
            h['points'] += 3
        elif match.home_score < match.away_score:
            a['wins'] += 1
            h['losses'] += 1
            a['points'] += 3
        else:
            h['draws'] += 1
            a['draws'] += 1
            h['points'] += 1
            a['points'] += 1

    for row in stats.values():
        row['goal_diff'] = row['goals_for'] - row['goals_against']

    return sorted(
        stats.values(),
        key=lambda x: (-x['points'], -x['goal_diff'], -x['goals_for'], -x['wins'], x['player'].user.username.lower()),
    )


def official_played_matches():
    return Match.objects.select_related('home_player__user', 'away_player__user').filter(match_type='official', status='played')


def top_scorers(limit=10):
    stats = compute_player_stats(official_played_matches())
    return sorted(stats, key=lambda x: (x['goals_for'], x['points']), reverse=True)[:limit]


def best_defenders(limit=10):
    stats = [row for row in compute_player_stats(official_played_matches()) if row['played'] > 0]
    return sorted(stats, key=lambda x: (x['goals_against'], -x['played'], -x['points'], x['player'].user.username.lower()))[:limit]


def division_standings(division):
    players = PlayerProfile.objects.filter(division_memberships__division=division, division_memberships__is_active=True).select_related('user')
    matches = division.matches.select_related('home_player__user', 'away_player__user').filter(match_type='official')
    return compute_player_stats(matches, players=players)


def season_outcomes(season):
    """Season verdict following league football rules.

    - The winner of the first division is the league champion.
    - The top 2 of every lower division are promoted to the division above.
    - The bottom 2 of every division are relegated to the division below
      (when one exists).
    """
    divisions = list(season.divisions.order_by('order', 'name'))
    rows = []
    for index, division in enumerate(divisions):
        standings = division_standings(division)
        count = len(standings)
        for rank, row in enumerate(standings, start=1):
            outcome = 'Safe'
            target = None
            if index == 0 and rank == 1:
                outcome = 'Champion'
            elif index == 0 and rank == 2:
                outcome = 'Runner-up'
            elif index > 0 and rank <= 2:
                outcome = 'Promoted'
                target = divisions[index - 1]
            if count >= 4 and rank > count - 2:
                if index < len(divisions) - 1:
                    outcome = 'Relegated'
                    target = divisions[index + 1]
                else:
                    outcome = 'Relegation zone'
            rows.append({
                'division': division,
                'rank': rank,
                'player': row['player'],
                'stats': row,
                'outcome': outcome,
                'target': target,
            })
    return rows


def tournament_group_stats(matches, players):
    return compute_player_stats(matches, players=players)
