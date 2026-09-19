"""Test combat policy improvements for MarineMicro scenarios."""
import asyncio
from player import decide


class MockJev:
    """Mock Jev that always chooses the first option."""
    def __init__(self):
        self.calls = []
        self.cost = 0
    
    async def ask(self, state, questions):
        """Record calls and return first option for each question."""
        self.calls.append({'state': state, 'questions': questions})
        answers = {}
        for key, question in questions.items():
            criteria = question.get('criteria', {})
            if criteria:
                first_key = next(iter(criteria.keys()))
                answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
        return answers
    
    def log(self, event, **kwargs):
        """Record log events."""
        pass


def test_continue_omitted_when_idle_units_face_nearby_threats():
    """Continue should not be offered for positioning/combat when units are idle and enemies are visible."""
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Marine', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [],  # Idle
                'candidates': [
                    {'id': 'attack_1234', 'description': 'Attack target 1234',
                     'command': {'unit_tag': 1001, 'ability_id': 3674, 'target_unit_tag': 1234}},
                ]
            }
        ]
    }
    
    memory = {}
    jev = MockJev()
    
    commands = asyncio.run(decide(view, jev, memory))
    
    # Check that a question was asked
    assert len(jev.calls) > 0
    
    # Find the Marine selection question
    marine_question = None
    for call in jev.calls:
        for key, question in call['questions'].items():
            if 'Marine' in key or any('Marine' in str(c) for c in question.get('criteria', {}).values()):
                marine_question = question
                break
    
    # Continue should NOT be in the criteria when units are idle and enemies are nearby
    assert marine_question is not None, "Should have a Marine-related question"
    criteria_keys = list(marine_question['criteria'].keys())
    assert 'continue' not in criteria_keys, "Continue should be omitted when idle units face nearby threats"


def test_continue_suppressed_when_attack_orders_in_engagement():
    """Engagement plus Attack queues still suppress continue for combat/positioning."""
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Marine', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [{'ability': 'Attack'}],
                'candidates': [
                    {'id': 'attack_1234', 'description': 'Attack target 1234',
                     'command': {'unit_tag': 1001, 'ability_id': 3674, 'target_unit_tag': 1234}},
                ]
            }
        ]
    }
    
    memory = {}
    jev = MockJev()
    
    commands = asyncio.run(decide(view, jev, memory))
    
    assert len(jev.calls) > 0
    
    marine_question = None
    for call in jev.calls:
        for key, question in call['questions'].items():
            if key == 'Marine':
                marine_question = question
                break
    
    assert marine_question is not None, "Should have a Marine order question"
    criteria_keys = list(marine_question['criteria'].keys())
    assert 'continue' not in criteria_keys, "Continue should be suppressed in engagement even with Attack orders"


def test_continue_offered_when_no_visible_enemies():
    """Continue should be offered when idle but no enemies are visible anywhere."""
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [],  # No enemies at all
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [],  # Idle
                'candidates': [
                    {'id': 'north', 'description': 'Move north',
                     'command': {'unit_tag': 1001, 'ability_id': 16, 'point': [3.0, 4.0]}},
                ]
            }
        ]
    }
    
    memory = {}
    jev = MockJev()
    
    commands = asyncio.run(decide(view, jev, memory))
    
    # Check that a question was asked
    assert len(jev.calls) > 0
    
    # Find the Marine selection question
    marine_question = None
    for call in jev.calls:
        for key, question in call['questions'].items():
            if 'Marine' in key or any('Marine' in str(c) for c in question.get('criteria', {}).values()):
                marine_question = question
                break
    
    # Continue SHOULD be in the criteria when no enemies are visible
    assert marine_question is not None, "Should have a Marine-related question"
    criteria_keys = list(marine_question['criteria'].keys())
    assert 'continue' in criteria_keys, "Continue should be offered when no visible enemies"


def test_combat_actions_highlighted_with_nearby_enemies():
    """Combat actions should be highlighted with [COMBAT] prefix when enemies are nearby."""
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Marine', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [],
                'candidates': [
                    {'id': 'attack_1234', 'description': 'Attack target 1234 at [5.0, 5.0], distance 2.8',
                     'command': {'unit_tag': 1001, 'ability_id': 3674, 'target_unit_tag': 1234,
                                'point': [5.0, 5.0]}},
                ]
            }
        ]
    }
    
    memory = {}
    jev = MockJev()
    
    commands = asyncio.run(decide(view, jev, memory))
    
    # Check that questions were asked
    assert len(jev.calls) > 0
    
    # Look for combat-related descriptions in any question
    found_combat_prefix = False
    for call in jev.calls:
        for key, question in call['questions'].items():
            for criterion_key, criterion_desc in question.get('criteria', {}).items():
                if criterion_key.startswith('group_attack') and 'COMBAT' in str(criterion_desc):
                    found_combat_prefix = True
                    break
    
    assert found_combat_prefix, "Combat actions should be highlighted with COMBAT prefix when enemies are nearby"


def test_positioning_continue_omitted_when_idle_with_visible_enemies():
    """Continue should not be offered for positioning purpose when idle with visible enemies."""
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Marine', 'alliance': 'Enemy', 'position': [20.0, 20.0]}  # Far away but visible
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [],  # Idle
                'candidates': [
                    {'id': 'north', 'description': 'Move north',
                     'command': {'unit_tag': 1001, 'ability_id': 16, 'point': [3.0, 4.0]}},
                ]
            }
        ]
    }
    
    class PositioningJev(MockJev):
        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    assert 'continue' not in criteria
                    answers[key] = {'choice': 'positioning', 'probabilities': {'positioning': 1.0}}
                elif key == 'Marine':
                    criteria_keys = list(criteria.keys())
                    assert 'continue' not in criteria_keys, f"Continue should be omitted for positioning when idle with visible enemies. Got: {criteria_keys}"
                    answers[key] = {'choice': 'group_north', 'probabilities': {'group_north': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    jev = PositioningJev()
    commands = asyncio.run(decide(view, jev, {}))
    assert commands == [{'unit_tag': 1001, 'ability_id': 16, 'point': [3.0, 4.0]}]


def test_combat_guidance_added_to_instructions():
    """Instructions should include combat guidance when threats are nearby."""
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Zergling', 'alliance': 'Enemy', 'position': [5.0, 5.0]},
            {'type': 'Zergling', 'alliance': 'Enemy', 'position': [5.5, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [],  # Idle
                'candidates': [
                    {'id': 'attack_1234', 'description': 'Attack target 1234',
                     'command': {'unit_tag': 1001, 'ability_id': 3674, 'target_unit_tag': 1234}},
                ]
            }
        ]
    }
    
    memory = {}
    jev = MockJev()
    
    commands = asyncio.run(decide(view, jev, memory))
    
    # Check that questions include combat guidance
    found_combat_guidance = False
    for call in jev.calls:
        for key, question in call['questions'].items():
            instructions = question.get('instructions', '')
            if 'COMBAT SITUATION' in instructions:
                found_combat_guidance = True
                assert 'Zergling' in instructions
                assert 'Prioritize engagement over inaction' in instructions
                break
    
    assert found_combat_guidance, "Instructions should include combat situation guidance when threats are nearby"


def test_positioning_with_only_move_orders_omits_continue_when_enemies_visible():
    """Continue is a no-op for positioning when the queue is only Move and enemies are visible."""
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Zergling', 'alliance': 'Enemy', 'position': [20.0, 20.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [{'ability': 'Move Move'}],
                'candidates': [
                    {'id': 'north', 'description': 'Move north',
                     'command': {'unit_tag': 1001, 'ability_id': 16, 'point': [3.0, 4.0]}},
                    {'id': 'attack_move_east', 'description': 'Attack-move east',
                     'command': {'unit_tag': 1001, 'ability_id': 23, 'point': [8.0, 3.0]}},
                ]
            }
        ]
    }

    class PositioningJev(MockJev):
        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    assert 'continue' not in criteria
                    assert 'Attack or Attack-Move' in criteria.get('combat', '')
                    answers[key] = {'choice': 'positioning', 'probabilities': {'positioning': 1.0}}
                elif key == 'Marine':
                    assert 'continue' not in criteria
                    answers[key] = {'choice': 'group_north', 'probabilities': {'group_north': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    jev = PositioningJev()
    commands = asyncio.run(decide(view, jev, {}))
    assert commands == [{'unit_tag': 1001, 'ability_id': 16, 'point': [3.0, 4.0]}]


def test_continue_allowed_when_attack_orders_are_already_useful():
    """Out of engagement, Attack queues may still offer continue."""
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [{'ability': 'Attack Attack'}],
                'candidates': [
                    {'id': 'attack_1234', 'description': 'Attack target 1234',
                     'command': {'unit_tag': 1001, 'ability_id': 3674, 'target_unit_tag': 1234}},
                ]
            }
        ]
    }

    logs = []

    class CombatContinueJev(MockJev):
        def log(self, event, **fields):
            logs.append((event, fields))

        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    answers[key] = {'choice': 'combat', 'probabilities': {'combat': 1.0}}
                elif key == 'Marine':
                    assert 'continue' in criteria
                    answers[key] = {'choice': 'continue', 'probabilities': {'continue': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    jev = CombatContinueJev()
    commands = asyncio.run(decide(view, jev, {}))
    assert commands == []
    allowed = [fields for event, fields in logs if event == 'continue_allowed']
    assert allowed
    assert allowed[0]['current_order_counts'] == {'Attack Attack': 1}


def test_combat_purpose_in_engagement_reissues_attack_despite_existing_queue():
    """Combat purpose in engagement suppresses continue even when Attack is already queued."""
    attack = {'unit_tag': 1001, 'ability_id': 3674, 'target_unit_tag': 1234}
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Zergling', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [
            {
                'tag': 1001,
                'type': 'Marine',
                'position': [3.0, 3.0],
                'health': 45,
                'health_fraction': 1.0,
                'build_progress': 1.0,
                'orders': [{'ability': 'Attack Attack'}],
                'candidates': [
                    {'id': 'attack_1234', 'description': 'Attack target 1234',
                     'command': attack},
                ]
            }
        ]
    }

    logs = []

    class CombatReissueJev(MockJev):
        def log(self, event, **fields):
            logs.append((event, fields))

        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    answers[key] = {'choice': 'combat', 'probabilities': {'combat': 1.0}}
                elif key == 'Marine':
                    assert 'continue' not in criteria
                    answers[key] = {'choice': 'group_attack_1234', 'probabilities': {'group_attack_1234': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    jev = CombatReissueJev()
    commands = asyncio.run(decide(view, jev, {}))
    assert commands == [attack]
    suppressed = [fields for event, fields in logs if event == 'continue_suppressed']
    assert suppressed
    assert suppressed[0]['current_order_counts'] == {'Attack Attack': 1}
    assert suppressed[0]['purpose'] == 'combat'


def _marine_with_stop_hold_and_attack(tag=1001, health_fraction=1.0, orders=None, extra_candidates=None):
    attack = {'unit_tag': tag, 'ability_id': 3674, 'target_unit_tag': 1234}
    stop = {'unit_tag': tag, 'ability_id': 4}
    hold = {'unit_tag': tag, 'ability_id': 18}
    north = {'unit_tag': tag, 'ability_id': 16, 'point': [3.0, 9.0]}
    attack_move = {'unit_tag': tag, 'ability_id': 23, 'point': [9.0, 3.0]}
    candidates = [
        {'id': 'stop', 'description': 'Stop the current order; normal automatic targeting remains possible',
         'command': stop},
        {'id': 'hold_position', 'description': 'Hold position here instead of continuing the current movement order',
         'command': hold},
        {'id': 'north', 'description': 'Move north', 'command': north},
        {'id': 'attack_1234', 'description': 'Attack visible Zergling tag 1234, distance 2.8',
         'command': attack},
        {'id': 'attack_move_east', 'description': 'Attack-move east', 'command': attack_move},
    ]
    if extra_candidates:
        candidates.extend(extra_candidates)
    unit = {
        'tag': tag,
        'type': 'Marine',
        'position': [3.0, 3.0],
        'health': 45 * health_fraction,
        'health_fraction': health_fraction,
        'build_progress': 1.0,
        'orders': orders or [],
        'candidates': candidates,
    }
    return unit, attack, stop, hold, north


def test_positioning_omits_stop_and_hold_when_attack_available_in_engagement():
    """Stop/Hold must not be choosable as positioning while Attack is also offered in engagement."""
    unit, attack, stop, hold, north = _marine_with_stop_hold_and_attack()
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Zergling', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [unit],
    }
    logs = []

    class PositioningJev(MockJev):
        def log(self, event, **fields):
            logs.append((event, fields))

        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    answers[key] = {'choice': 'positioning', 'probabilities': {'positioning': 1.0}}
                elif key == 'Marine':
                    assert 'group_stop' not in criteria, f'Stop should be omitted in engagement. Got: {list(criteria)}'
                    assert 'group_hold_position' not in criteria
                    assert 'group_north' in criteria
                    assert 'group_attack_1234' not in criteria
                    answers[key] = {'choice': 'group_north', 'probabilities': {'group_north': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    commands = asyncio.run(decide(view, PositioningJev(), {}))
    assert commands == [north]
    omitted = [fields for event, fields in logs if event == 'stop_hold_suppressed']
    assert omitted
    assert set(omitted[0]['omitted']) >= {'group_stop', 'group_hold_position'}


def test_combat_keeps_tagged_attack_and_omits_stop():
    """group_attack_<tag> stays; Stop is not a combat implementation in engagement."""
    unit, attack, stop, hold, north = _marine_with_stop_hold_and_attack()
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Zergling', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [unit],
    }

    class CombatJev(MockJev):
        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    answers[key] = {'choice': 'combat', 'probabilities': {'combat': 1.0}}
                elif key == 'Marine':
                    assert 'group_attack_1234' in criteria
                    assert 'group_attack_move_east' in criteria
                    assert 'group_stop' not in criteria
                    assert 'group_hold_position' not in criteria
                    answers[key] = {'choice': 'group_attack_1234', 'probabilities': {'group_attack_1234': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    commands = asyncio.run(decide(view, CombatJev(), {}))
    assert commands == [attack]


def test_stop_and_hold_remain_when_not_in_engagement():
    """Out of engagement, Stop/Hold stay available as positioning."""
    unit, attack, stop, hold, north = _marine_with_stop_hold_and_attack()
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [unit],
    }

    class PositioningJev(MockJev):
        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    answers[key] = {'choice': 'positioning', 'probabilities': {'positioning': 1.0}}
                elif key == 'Marine':
                    assert 'group_stop' in criteria
                    assert 'group_hold_position' in criteria
                    answers[key] = {'choice': 'group_stop', 'probabilities': {'group_stop': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    commands = asyncio.run(decide(view, PositioningJev(), {}))
    assert commands == [stop]


def test_stop_remains_in_engagement_when_no_attack_is_offered():
    """Only omit Stop/Hold when Attack is also on the menu."""
    unit, attack, stop, hold, north = _marine_with_stop_hold_and_attack()
    unit['candidates'] = [c for c in unit['candidates'] if 'attack' not in c['id']]
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Zergling', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [unit],
    }

    class PositioningJev(MockJev):
        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    assert 'combat' not in criteria
                    answers[key] = {'choice': 'positioning', 'probabilities': {'positioning': 1.0}}
                elif key == 'Marine':
                    assert 'group_stop' in criteria
                    assert 'group_hold_position' in criteria
                    answers[key] = {'choice': 'group_stop', 'probabilities': {'group_stop': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    commands = asyncio.run(decide(view, PositioningJev(), {}))
    assert commands == [stop]


def test_damaged_units_omit_stop_without_visible_enemies():
    """Damaged selections are in engagement; Stop is omitted if Attack-Move is offered."""
    unit, attack, stop, hold, north = _marine_with_stop_hold_and_attack(health_fraction=0.4)
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [unit],
    }

    class CombatJev(MockJev):
        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    positioning = criteria.get('positioning', '')
                    assert 'Stop and Hold Position are omitted' in positioning
                    answers[key] = {'choice': 'combat', 'probabilities': {'combat': 1.0}}
                elif key == 'Marine':
                    assert 'group_stop' not in criteria
                    assert 'group_hold_position' not in criteria
                    assert 'group_attack_move_east' in criteria
                    answers[key] = {'choice': 'group_attack_move_east',
                                    'probabilities': {'group_attack_move_east': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    commands = asyncio.run(decide(view, CombatJev(), {}))
    assert commands == [{'unit_tag': 1001, 'ability_id': 23, 'point': [9.0, 3.0]}]


def test_join_still_offered_when_hold_is_omitted_in_engagement():
    """Regroup uses Hold internally but is not itself Hold Position."""
    enemy = {'type': 'Zergling', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
    units = []
    for tag, other in [(1, 2), (2, 1)]:
        units.append({
            'tag': tag,
            'type': 'Marine',
            'position': [float(tag), 0.0],
            'health': 45,
            'health_fraction': 1.0,
            'build_progress': 1.0,
            'orders': [],
            'candidates': [
                {'id': 'stop', 'description': 'Stop',
                 'command': {'unit_tag': tag, 'ability_id': 4}},
                {'id': 'hold_position', 'description': 'Hold position',
                 'command': {'unit_tag': tag, 'ability_id': 18}},
                {'id': f'join_{other}', 'description': f'Join {other}',
                 'command': {'unit_tag': tag, 'ability_id': 16, 'point': [float(other), 0.0]}},
                {'id': 'attack_1234', 'description': 'Attack target 1234',
                 'command': {'unit_tag': tag, 'ability_id': 3674, 'target_unit_tag': 1234}},
            ],
        })
    view = {
        'loop': 1,
        'objective': 'Test',
        'resources': {},
        'visible_entities': [enemy],
        'self': units,
    }

    class JoinJev(MockJev):
        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    answers[key] = {'choice': 'positioning', 'probabilities': {'positioning': 1.0}}
                elif key == 'Marine':
                    assert 'group_join_1' in criteria
                    assert 'group_stop' not in criteria
                    assert 'group_hold_position' not in criteria
                    answers[key] = {'choice': 'group_join_1', 'probabilities': {'group_join_1': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    commands = asyncio.run(decide(view, JoinJev(), {}))
    assert commands == [{'unit_tag': 1, 'ability_id': 18},
                        {'unit_tag': 2, 'ability_id': 16, 'point': [1.0, 0.0]}]


def test_individual_omits_stop_and_hold_when_attack_and_enemies():
    """Individual menus drop Stop/Hold the same way group menus do."""
    unit, attack, stop, hold, north = _marine_with_stop_hold_and_attack()
    unit['surroundings'] = [
        {'tag': 1234, 'type': 'Zergling', 'alliance': 'Enemy', 'distance': 2.8,
         'east_offset': 2.0, 'north_offset': 2.0}
    ]
    view = {
        'loop': 100,
        'objective': 'Test objective',
        'resources': {'minerals': 100, 'vespene': 0},
        'explored_map': {'rows_north_to_south': ['...'], 'bounds': [0, 0, 10, 10]},
        'visible_entities': [
            {'type': 'Zergling', 'alliance': 'Enemy', 'position': [5.0, 5.0]}
        ],
        'last_known_entities': [],
        'unit_type_facts': {'Marine': {'catalog_weapons': []}},
        'self': [unit],
    }
    logs = []

    class IndividualJev(MockJev):
        def log(self, event, **fields):
            logs.append((event, fields))

        async def ask(self, state, questions):
            self.calls.append({'state': state, 'questions': questions})
            answers = {}
            for key, question in questions.items():
                criteria = question.get('criteria', {})
                if key == 'purpose_Marine':
                    answers[key] = {'choice': 'individual', 'probabilities': {'individual': 1.0}}
                elif key == '1001':
                    assert 'stop' not in criteria
                    assert 'hold_position' not in criteria
                    assert 'attack_1234' in criteria
                    answers[key] = {'choice': 'attack_1234', 'probabilities': {'attack_1234': 1.0}}
                elif criteria:
                    first_key = next(iter(criteria.keys()))
                    answers[key] = {'choice': first_key, 'probabilities': {first_key: 1.0}}
            return answers

    commands = asyncio.run(decide(view, IndividualJev(), {}))
    assert commands == [attack]
    omitted = [fields for event, fields in logs if event == 'stop_hold_suppressed']
    assert any('stop' in fields.get('omitted', []) or 'group_stop' in fields.get('omitted', [])
               for fields in omitted)
