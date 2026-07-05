"""Pure football scheduling logic: round-robin calendars, group draws and
FIFA-style knockout brackets.

All functions are pure (no database access) so they can be unit-tested and
reused for both league divisions and tournament groups.
"""


def round_robin_rounds(players, double_round=False):
    """Build a round-robin schedule using the circle method.

    Returns a list of (round_number, home, away) tuples where every player
    plays exactly once per round (one player rests per round when the count
    is odd). With ``double_round`` each pairing is mirrored in the second
    half of the season (home/away swapped), like a real football league.

    For n players: n-1 rounds (n even) or n rounds (n odd), n//2 matches per
    round; a double round-robin doubles the number of rounds.
    """
    players = list(players)
    if len(players) < 2:
        return []

    rotation = list(players)
    if len(rotation) % 2 == 1:
        rotation.append(None)  # bye marker
    half = len(rotation) // 2
    round_count = len(rotation) - 1

    first_leg = []
    for round_number in range(1, round_count + 1):
        pairs = []
        for index in range(half):
            home, away = rotation[index], rotation[-1 - index]
            if home is None or away is None:
                continue
            # Alternate venue for the fixed first seat so the same player
            # does not host every round.
            if index == 0 and round_number % 2 == 0:
                home, away = away, home
            pairs.append((round_number, home, away))
        first_leg.extend(pairs)
        # rotate all but the first seat
        rotation = [rotation[0]] + [rotation[-1]] + rotation[1:-1]

    if not double_round:
        return first_leg

    second_leg = [(round_number + round_count, away, home) for round_number, home, away in first_leg]
    return first_leg + second_leg


def rounds_count(player_count, double_round=False):
    """Number of rounds a round-robin schedule needs."""
    if player_count < 2:
        return 0
    base = player_count - 1 if player_count % 2 == 0 else player_count
    return base * 2 if double_round else base


def serpentine_groups(seeded_players, group_count):
    """Distribute ranked players into groups using pot-based snake seeding.

    ``seeded_players`` must be ordered from strongest to weakest. Players are
    split into pots of ``group_count`` (pot 1 = top seeds, like FIFA pots)
    and each pot is dealt across the groups, reversing direction on odd pots
    so total strength stays balanced.

    Returns a list of ``group_count`` lists.
    """
    groups = [[] for _ in range(group_count)]
    pots = [seeded_players[i:i + group_count] for i in range(0, len(seeded_players), group_count)]
    for pot_index, pot in enumerate(pots):
        ordered = range(group_count) if pot_index % 2 == 0 else reversed(range(group_count))
        for group_index, player in zip(ordered, pot):
            groups[group_index].append(player)
    return groups


def knockout_pairings(group_results):
    """Build first-round knockout pairings from group results, FIFA style.

    ``group_results`` is an ordered list (group A first) of (winner,
    runner_up) tuples. Pairings cross winners with runners-up of the
    neighbouring group so two players from the same group can only meet
    again in the final:

    - 2 groups  -> semi-finals:      A1-B2, B1-A2
    - 4 groups  -> quarter-finals:   A1-B2, C1-D2, B1-A2, D1-C2
    - 8 groups  -> round of 16:      A1-B2, C1-D2, E1-F2, G1-H2,
                                     B1-A2, D1-C2, F1-E2, H1-G2

    The order of the returned list is the bracket order: match 1 winner
    plays match 2 winner in the next round, and so on.
    """
    group_count = len(group_results)
    if group_count not in {2, 4, 8}:
        raise ValueError(f'{group_count} groups cannot feed a standard knockout bracket.')

    pairings = []
    # winners of even-indexed groups host runners-up of the following group
    for index in range(0, group_count, 2):
        pairings.append((group_results[index][0], group_results[index + 1][1]))
    for index in range(0, group_count, 2):
        pairings.append((group_results[index + 1][0], group_results[index][1]))

    # winners' half first, runners-up's half second: with sequential bracket
    # pairing (match 1 vs match 2, ...), two players from the same group can
    # only meet again in the final.
    return pairings


def stage_for_qualified(count):
    """Knockout stage name for a number of qualified players."""
    return {16: 'round_of_16', 8: 'quarter_final', 4: 'semi_final', 2: 'final'}.get(count)


def next_stage(stage):
    return {'round_of_16': 'quarter_final', 'quarter_final': 'semi_final', 'semi_final': 'final'}.get(stage)
