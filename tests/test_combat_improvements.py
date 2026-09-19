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


def test_continue_offered_when_units_have_orders():
    """Continue should be offered when units already have Attack orders, even with nearby enemies."""
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
                'orders': [{'ability': 'Attack'}],  # Has orders
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
    
    # Continue SHOULD be in the criteria when units already have orders
    assert marine_question is not None, "Should have a Marine-related question"
    criteria_keys = list(marine_question['criteria'].keys())
    assert 'continue' in criteria_keys, "Continue should be offered when units have existing orders"


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
    """Useful Attack queues still offer continue under visible enemies."""
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
                     'command': {'unit_tag': 1001, 'ability_id': 3674, 'target_unit_tag': 1234}},
                ]
            }
        ]
    }

    class CombatContinueJev(MockJev):
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
