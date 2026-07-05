"""Tournament domain logic: seeding, group draw, fixtures, knockout bracket.

Follows real football / FIFA conventions:
- groups of 4, snake-seeded from player rankings (pots);
- group fixtures generated with the circle method (home & away when the
  tournament uses two legs), everyone plays once per round;
- top 2 of each group qualify; with 2/4/8 groups the bracket uses the exact
  FIFA cross-pairings (A1-B2, B1-A2, ...) so group rivals can only meet again
  in the final; with other group counts the best third-placed players
  complete the bracket (UEFA Euro style);
- semi-final losers play a third-place match;
- knockout ties are decided on penalties (or a manual winner).
"""
from django.db import transaction

from .models import (
    Match,
    PlayerProfile,
    TournamentGroup,
    TournamentGroupMembership,
    TournamentMatch,
    TournamentParticipant,
)
from .scheduling import knockout_pairings, round_robin_rounds, serpentine_groups, stage_for_qualified, next_stage
from .utils import compute_player_stats, tournament_group_stats

GROUP_SIZE = 4
KNOCKOUT_SIZES = (2, 4, 8, 16)


def ranked_players(players):
    """Order players from strongest to weakest using overall played matches."""
    players = list(players)
    matches = Match.objects.select_related('home_player__user', 'away_player__user').filter(status='played')
    stats = {row['player'].id: row for row in compute_player_stats(matches, players=players)}
    return sorted(
        players,
        key=lambda player: (
            -stats[player.id]['points'],
            -stats[player.id]['goal_diff'],
            -stats[player.id]['wins'],
            -stats[player.id]['played'],
            player.user.username.lower(),
        ),
    )


def eligible_public_players():
    return PlayerProfile.objects.select_related('user').filter(user__is_active=True, is_public=True)


def selected_players(tournament):
    """Players chosen for the tournament, strongest first.

    Uses the tournament's own participants when at least 4 were chosen
    (private tournaments / manual selection); otherwise auto-selects from the
    global ranking of public active players (official tournaments).
    """
    chosen = [p.player for p in tournament.participants.select_related('player__user').filter(status='selected')]
    if len(chosen) >= GROUP_SIZE:
        return ranked_players(chosen), True
    return ranked_players(eligible_public_players()), False


@transaction.atomic
def generate_structure(tournament):
    """Generate groups + fixtures (or a direct bracket) for a tournament.

    Returns (selected_count, reserve_count, group_count). Raises ValueError
    with a user-facing message when the tournament cannot be generated.
    """
    players, manual_selection = selected_players(tournament)
    if len(players) < GROUP_SIZE:
        raise ValueError('At least 4 players are required to start a tournament.')

    max_players = min(32, tournament.max_participants or 32)
    capped = players[:max_players]

    if tournament.format == 'knockout':
        selected_count = max(size for size in KNOCKOUT_SIZES if size <= len(capped))
    elif tournament.format == 'league':
        selected_count = len(capped)
    else:
        selected_count = (len(capped) // GROUP_SIZE) * GROUP_SIZE

    selected = capped[:selected_count]
    reserves = capped[selected_count:] + players[max_players:]

    tournament.participants.all().delete()
    tournament.groups.all().delete()
    tournament.matches.all().delete()

    participants = []
    for seed, player in enumerate(selected, start=1):
        participants.append(TournamentParticipant.objects.create(tournament=tournament, player=player, seed=seed, status='selected'))
    for seed, player in enumerate(reserves, start=selected_count + 1):
        TournamentParticipant.objects.create(tournament=tournament, player=player, seed=seed, status='reserve')

    if tournament.format == 'knockout':
        _create_seeded_bracket(tournament, selected)
        tournament.groups_generated = True
        tournament.group_fixtures_generated = True
        tournament.knockout_generated = True
        tournament.status = 'knockout'
        tournament.save(update_fields=['groups_generated', 'group_fixtures_generated', 'knockout_generated', 'status', 'updated_at'])
        return selected_count, len(reserves), 0

    if tournament.format == 'league':
        group = TournamentGroup.objects.create(tournament=tournament, name='League')
        for participant in participants:
            TournamentGroupMembership.objects.create(group=group, participant=participant)
        group_count = 1
    else:
        group_count = selected_count // GROUP_SIZE
        groups = [TournamentGroup.objects.create(tournament=tournament, name=chr(65 + i)) for i in range(group_count)]
        for group, members in zip(groups, serpentine_groups(participants, group_count)):
            for participant in members:
                TournamentGroupMembership.objects.create(group=group, participant=participant)

    create_group_fixtures(tournament)
    tournament.groups_generated = True
    tournament.group_fixtures_generated = True
    tournament.status = 'group_stage'
    tournament.save(update_fields=['groups_generated', 'group_fixtures_generated', 'status', 'updated_at'])
    return selected_count, len(reserves), group_count


def create_group_fixtures(tournament):
    """Round-robin fixtures inside each group (home & away when 2 legs)."""
    double = tournament.group_legs == 2
    for group in tournament.groups.all():
        players = [m.participant.player for m in group.memberships.select_related('participant__player')]
        for round_number, home, away in round_robin_rounds(players, double_round=double):
            TournamentMatch.objects.get_or_create(
                tournament=tournament,
                group=group,
                stage='group',
                home_player=home,
                away_player=away,
                round_number=round_number,
                defaults={},
            )


def _create_seeded_bracket(tournament, seeded):
    """Direct-knockout bracket: seed 1 vs lowest seed, etc."""
    count = len(seeded)
    stage = stage_for_qualified(count)
    pairs = [(seeded[i], seeded[count - 1 - i]) for i in range(count // 2)]
    # standard bracket order keeps top seeds apart until the final
    order = _bracket_order(count // 2)
    for slot, index in enumerate(order):
        home, away = pairs[index]
        TournamentMatch.objects.create(
            tournament=tournament, stage=stage, round_number=1,
            home_player=home, away_player=away, bracket_slot=slot,
        )


def _bracket_order(n):
    """Seed-separated bracket positions for n first-round matches."""
    order = [0]
    while len(order) < n:
        doubled = []
        size = len(order) * 2
        for x in order:
            doubled.extend([x, size - 1 - x])
        order = doubled
    return order[:n] if n > 1 else [0]


def group_tables(tournament, played_only=True):
    """[(group, standings)] for every group, ordered by group name."""
    tables = []
    for group in tournament.groups.prefetch_related('memberships__participant__player__user').order_by('name'):
        players = [m.participant.player for m in group.memberships.all()]
        matches = group.matches.filter(status='played') if played_only else group.matches.all()
        tables.append((group, tournament_group_stats(matches.select_related('home_player__user', 'away_player__user'), players)))
    return tables


def qualified_for_knockout(tournament):
    """Return the first-round knockout pairings from final group tables."""
    tables = group_tables(tournament)
    group_count = len(tables)
    if group_count in {2, 4, 8}:
        results = [(table[0]['player'], table[1]['player']) for _, table in tables]
        return knockout_pairings(results)

    # Euro-style: complete with best third-placed players up to a bracket size
    qualified = []
    thirds = []
    for _, table in tables:
        qualified.append(table[0])
        qualified.append(table[1])
        if len(table) > 2:
            thirds.append(table[2])
    thirds.sort(key=lambda row: (-row['points'], -row['goal_diff'], -row['goals_for'], row['player'].user.username.lower()))
    target = next((size for size in KNOCKOUT_SIZES if size >= len(qualified)), None)
    if target is None:
        raise ValueError('Too many qualified players for a knockout bracket.')
    needed = target - len(qualified)
    if needed > len(thirds):
        raise ValueError('Not enough players to complete the knockout bracket.')
    qualified.extend(thirds[:needed])
    # seed by group performance, pair 1 vs N, 2 vs N-1, ...
    qualified.sort(key=lambda row: (-row['points'], -row['goal_diff'], -row['goals_for'], row['player'].user.username.lower()))
    players = [row['player'] for row in qualified]
    count = len(players)
    pairs = [(players[i], players[count - 1 - i]) for i in range(count // 2)]
    return [pairs[i] for i in _bracket_order(count // 2)]


@transaction.atomic
def generate_knockout_bracket(tournament):
    pairs = qualified_for_knockout(tournament)
    stage = stage_for_qualified(len(pairs) * 2)
    if stage is None:
        raise ValueError('Qualified players do not fit a standard knockout bracket.')
    for slot, (home, away) in enumerate(pairs):
        TournamentMatch.objects.create(
            tournament=tournament, stage=stage, round_number=1,
            home_player=home, away_player=away, bracket_slot=slot,
        )
    tournament.knockout_generated = True
    tournament.status = 'knockout'
    tournament.save(update_fields=['knockout_generated', 'status', 'updated_at'])
    return stage, len(pairs)


def resolve_winner(match):
    """Winner of a knockout match: score, then penalties, then manual pick."""
    if not match.has_score:
        return None
    if match.home_score > match.away_score:
        return match.home_player
    if match.away_score > match.home_score:
        return match.away_player
    if match.went_to_penalties and match.home_penalties != match.away_penalties:
        return match.home_player if match.home_penalties > match.away_penalties else match.away_player
    return match.winner


def maybe_complete_league(tournament):
    """League-format tournaments finish when every fixture is played."""
    if tournament.format != 'league':
        return
    if tournament.matches.exclude(status='played').exists():
        return
    tables = group_tables(tournament)
    if tables and tables[0][1]:
        tournament.champion = tables[0][1][0]['player']
        tournament.status = 'completed'
        tournament.save(update_fields=['champion', 'status', 'updated_at'])


def advance_knockout(tournament):
    """Create the next knockout round when the current one is complete.

    Semi-final losers meet in a third-place match. The champion is crowned
    when the final is played.
    """
    for stage in ['round_of_16', 'quarter_final', 'semi_final', 'final']:
        matches = list(tournament.matches.filter(stage=stage).order_by('bracket_slot', 'id'))
        if not matches or any(m.status != 'played' or not m.winner for m in matches):
            continue
        if stage == 'final':
            if tournament.champion_id != matches[0].winner_id or tournament.status != 'completed':
                tournament.champion = matches[0].winner
                tournament.status = 'completed'
                tournament.save(update_fields=['champion', 'status', 'updated_at'])
            return
        target = next_stage(stage)
        if tournament.matches.filter(stage=target).exists():
            continue
        round_number = matches[0].round_number + 1
        for slot, idx in enumerate(range(0, len(matches), 2)):
            TournamentMatch.objects.create(
                tournament=tournament, stage=target, round_number=round_number,
                home_player=matches[idx].winner, away_player=matches[idx + 1].winner,
                bracket_slot=slot,
            )
        if stage == 'semi_final' and not tournament.matches.filter(stage='third_place').exists():
            losers = [m.away_player if m.winner_id == m.home_player_id else m.home_player for m in matches]
            if len(losers) == 2:
                TournamentMatch.objects.create(
                    tournament=tournament, stage='third_place', round_number=round_number,
                    home_player=losers[0], away_player=losers[1],
                )
        return
