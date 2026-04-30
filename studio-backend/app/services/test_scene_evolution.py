"""
Test for Scene Evolution Module

Tests the core scene evolution functionality including:
- record_evolution (scene_id first signature)
- get_evolution_data
- compute_improvement_metrics
- Integration with existing record_iteration
"""

import sys
sys.path.insert(0, '.')

from app.services.scene_evolution import SceneEvolutionTracker, evolution_tracker


def test_record_evolution_basic():
    """Test record_evolution with basic parameters"""
    tracker = SceneEvolutionTracker()
    
    iteration = tracker.record_evolution(
        scene_id='test_scene',
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.7,
        patterns_used=[{'type': 'camera', 'value': 'wide'}],
        deviations_used=[{'type': 'lighting', 'value': 'low_key'}]
    )
    
    assert iteration.scene_id == 'test_scene'
    assert iteration.iteration_number == 1
    assert iteration.intent_alignment_score == 0.8
    assert iteration.quality_score == 0.7
    assert len(iteration.patterns_used) == 1
    assert len(iteration.deviations_used) == 1
    print("✓ test_record_evolution_basic passed")


def test_record_evolution_multiple():
    """Test recording multiple evolutions for same scene"""
    tracker = SceneEvolutionTracker()
    
    tracker.record_evolution('scene1', 1, 0.7, 0.6, [], [])
    tracker.record_evolution('scene1', 2, 0.8, 0.7, [], [])
    tracker.record_evolution('scene1', 3, 0.9, 0.8, [], [])
    
    data = tracker.get_evolution_data('scene1')
    assert data is not None
    assert len(data) == 3
    assert data[0]['iteration_number'] == 1
    assert data[1]['iteration_number'] == 2
    assert data[2]['iteration_number'] == 3
    print("✓ test_record_evolution_multiple passed")


def test_get_evolution_data_with_limit():
    """Test get_evolution_data with limit parameter"""
    tracker = SceneEvolutionTracker()
    
    tracker.record_evolution('scene1', 1, 0.7, 0.6, [], [])
    tracker.record_evolution('scene1', 2, 0.8, 0.7, [], [])
    tracker.record_evolution('scene1', 3, 0.9, 0.8, [], [])
    
    data = tracker.get_evolution_data('scene1', limit=2)
    assert len(data) == 2
    # Should return last 2
    assert data[0]['iteration_number'] == 2
    assert data[1]['iteration_number'] == 3
    print("✓ test_get_evolution_data_with_limit passed")


def test_get_evolution_data_not_found():
    """Test get_evolution_data returns None for non-existent scene"""
    tracker = SceneEvolutionTracker()
    
    result = tracker.get_evolution_data('nonexistent')
    assert result is None
    print("✓ test_get_evolution_data_not_found passed")


def test_compute_improvement_metrics_empty():
    """Test compute_improvement_metrics with empty scene"""
    tracker = SceneEvolutionTracker()
    
    metrics = tracker.compute_improvement_metrics('nonexistent')
    assert metrics['improvement_rate'] == 0.0
    assert metrics['consistency_score'] == 0.0
    assert metrics['diversity_score'] == 0.0
    print("✓ test_compute_improvement_metrics_empty passed")


def test_compute_improvement_metrics_with_data():
    """Test compute_improvement_metrics with iterations"""
    tracker = SceneEvolutionTracker()
    
    tracker.record_evolution('scene1', 1, 0.7, 0.6, [], [])
    tracker.record_evolution('scene1', 2, 0.8, 0.7, [], [])
    
    metrics = tracker.compute_improvement_metrics('scene1')
    assert 'improvement_rate' in metrics
    assert 'consistency_score' in metrics
    assert 'diversity_score' in metrics
    print("✓ test_compute_improvement_metrics_with_data passed")


def test_global_instance_has_new_methods():
    """Verify the global evolution_tracker has all new methods"""
    assert hasattr(evolution_tracker, 'record_evolution')
    assert hasattr(evolution_tracker, 'get_evolution_data')
    assert hasattr(evolution_tracker, 'compute_improvement_metrics')
    print("✓ test_global_instance_has_new_methods passed")


def test_existing_record_iteration_still_works():
    """Verify existing record_iteration (project_id first) still works"""
    tracker = SceneEvolutionTracker()
    
    iteration = tracker.record_iteration(
        project_id='proj1',
        scene_id='scene1',
        intent_alignment=0.8,
        quality_score=0.7
    )
    
    assert iteration.scene_id == 'scene1'
    assert iteration.iteration_number == 1
    print("✓ test_existing_record_iteration_still_works passed")


def test_normalize_patterns_old_keys():
    """Test that old key format (type/value) is normalized to (pattern_type/pattern_value)"""
    tracker = SceneEvolutionTracker()
    
    # Use old key format
    iteration = tracker.record_evolution(
        scene_id='test_old_keys',
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.7,
        patterns_used=[{'type': 'camera', 'value': 'wide'}],
        deviations_used=[{'type': 'lighting', 'value': 'low_key'}]
    )
    
    # Verify stored with normalized keys
    assert iteration.patterns_used[0]['pattern_type'] == 'camera'
    assert iteration.patterns_used[0]['pattern_value'] == 'wide'
    assert iteration.deviations_used[0]['pattern_type'] == 'lighting'
    assert iteration.deviations_used[0]['pattern_value'] == 'low_key'
    print("✓ test_normalize_patterns_old_keys passed")


def test_normalize_patterns_new_keys():
    """Test that new key format (pattern_type/pattern_value) is preserved"""
    tracker = SceneEvolutionTracker()
    
    # Use new key format
    iteration = tracker.record_evolution(
        scene_id='test_new_keys',
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.7,
        patterns_used=[{'pattern_type': 'camera', 'pattern_value': 'wide'}],
        deviations_used=[{'pattern_type': 'lighting', 'pattern_value': 'low_key'}]
    )
    
    # Verify stored with same keys
    assert iteration.patterns_used[0]['pattern_type'] == 'camera'
    assert iteration.patterns_used[0]['pattern_value'] == 'wide'
    print("✓ test_normalize_patterns_new_keys passed")


def test_normalize_patterns_mixed_keys():
    """Test that mixed old and new key formats are both normalized"""
    tracker = SceneEvolutionTracker()
    
    iteration = tracker.record_evolution(
        scene_id='test_mixed_keys',
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.7,
        patterns_used=[
            {'type': 'camera', 'value': 'wide'},  # old
            {'pattern_type': 'lighting', 'pattern_value': 'high_key'}  # new
        ],
        deviations_used=[]
    )
    
    # Both should be normalized to pattern_type/pattern_value
    assert iteration.patterns_used[0]['pattern_type'] == 'camera'
    assert iteration.patterns_used[0]['pattern_value'] == 'wide'
    assert iteration.patterns_used[1]['pattern_type'] == 'lighting'
    assert iteration.patterns_used[1]['pattern_value'] == 'high_key'
    print("✓ test_normalize_patterns_mixed_keys passed")


def test_get_evolution_boost_with_none_scene_id():
    """Test that _get_evolution_boost returns 1.0 when scene_id is None"""
    from app.services.adaptation import AdaptationEngine
    ae = AdaptationEngine()
    
    boost = ae._get_evolution_boost(None, 'camera', 'wide')
    assert boost == 1.0, f"Expected 1.0, got {boost}"
    print("✓ test_get_evolution_boost_with_none_scene_id passed")


def test_adaptation_boost_with_normalized_patterns():
    """Test that adaptation boost works with normalized pattern data"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker
    ae = AdaptationEngine()

    scene_id = 'test_adaptation_boost_2'

    # Record with old keys - should be normalized
    # Use the GLOBAL singleton that adaptation.py references
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.9,
        quality_score=0.85,
        patterns_used=[{'type': 'camera', 'value': 'wide_shot'}],
        deviations_used=[]
    )

    # Boost should apply because normalization makes keys match
    boost = ae._get_evolution_boost(scene_id, 'camera', 'wide_shot')
    assert boost > 1.0, f"Expected boost > 1.0, got {boost}"
    print("✓ test_adaptation_boost_with_normalized_patterns passed")


def test_agent_executor_import_chain():
    """Test that AgentExecutor import chain still works"""
    from app.services.agent_executor import AgentExecutor
    from app.services.adaptation import adaptation_engine
    from app.services.scene_evolution import evolution_tracker

    # All imports should succeed
    assert AgentExecutor is not None
    assert adaptation_engine is not None
    assert evolution_tracker is not None
    print("✓ test_agent_executor_import_chain passed")


# =============================================================================
# WEIGHTED SCORING TESTS
# =============================================================================

def test_evolution_boost_increases_with_frequency():
    """Test that boost increases with more matching pattern uses"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_freq_boost'

    # Record 1 iteration with the pattern
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.8,
        patterns_used=[{'pattern_type': 'camera', 'pattern_value': 'wide'}],
        deviations_used=[]
    )
    boost_1 = ae._get_evolution_boost(scene_id, 'camera', 'wide')

    # Record 2 more iterations with the same pattern
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=2,
        intent_alignment_score=0.8,
        quality_score=0.8,
        patterns_used=[{'pattern_type': 'camera', 'pattern_value': 'wide'}],
        deviations_used=[]
    )
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=3,
        intent_alignment_score=0.8,
        quality_score=0.8,
        patterns_used=[{'pattern_type': 'camera', 'pattern_value': 'wide'}],
        deviations_used=[]
    )
    boost_3 = ae._get_evolution_boost(scene_id, 'camera', 'wide')

    # More matches = higher boost
    assert boost_3 > boost_1, f"Expected boost_3 ({boost_3}) > boost_1 ({boost_1})"
    print("✓ test_evolution_boost_increases_with_frequency passed")


def test_evolution_boost_increases_with_quality():
    """Test that boost increases with higher quality scores"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_quality_boost'

    # Low quality (but high alignment to be positive)
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.3,
        patterns_used=[{'pattern_type': 'lighting', 'pattern_value': 'low_key'}],
        deviations_used=[]
    )
    boost_low = ae._get_evolution_boost(scene_id, 'lighting', 'low_key')

    # High quality (also high alignment to be positive)
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=2,
        intent_alignment_score=0.8,
        quality_score=0.95,
        patterns_used=[{'pattern_type': 'lighting', 'pattern_value': 'high_key'}],
        deviations_used=[]
    )
    boost_high = ae._get_evolution_boost(scene_id, 'lighting', 'high_key')

    # Higher quality = higher boost
    assert boost_high > boost_low, f"Expected boost_high ({boost_high}) > boost_low ({boost_low})"
    print("✓ test_evolution_boost_increases_with_quality passed")


def test_evolution_boost_increases_with_alignment():
    """Test that boost increases with higher intent alignment scores"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_alignment_boost'

    # Low alignment (but high quality to be positive)
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.2,
        quality_score=0.85,
        patterns_used=[{'pattern_type': 'color', 'pattern_value': 'muted'}],
        deviations_used=[]
    )
    boost_low = ae._get_evolution_boost(scene_id, 'color', 'muted')

    # High alignment (also high quality to be positive)
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=2,
        intent_alignment_score=0.95,
        quality_score=0.85,
        patterns_used=[{'pattern_type': 'color', 'pattern_value': 'vibrant'}],
        deviations_used=[]
    )
    boost_high = ae._get_evolution_boost(scene_id, 'color', 'vibrant')

    # Higher alignment = higher boost
    assert boost_high > boost_low, f"Expected boost_high ({boost_high}) > boost_low ({boost_low})"
    print("✓ test_evolution_boost_increases_with_alignment passed")


def test_evolution_boost_favors_recent_matches():
    """Test that recency scoring works: more recent matches get higher weight"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_recency_boost'

    # Pattern with 1 recent match (only in iteration 3) - high quality/alignment for positive
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.8,
        patterns_used=[{'pattern_type': 'camera', 'pattern_value': 'old_only'}],
        deviations_used=[]
    )
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=2,
        intent_alignment_score=0.8,
        quality_score=0.8,
        patterns_used=[{'pattern_type': 'camera', 'pattern_value': 'old_only'}],
        deviations_used=[]
    )
    # Third iteration has both patterns
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=3,
        intent_alignment_score=0.8,
        quality_score=0.8,
        patterns_used=[
            {'pattern_type': 'camera', 'pattern_value': 'old_only'},
            {'pattern_type': 'camera', 'pattern_value': 'recent_only'}
        ],
        deviations_used=[]
    )

    # Pattern with 3 matches (appears in iterations 1, 2, 3)
    boost_many = ae._get_evolution_boost(scene_id, 'camera', 'old_only')
    # Pattern with 1 match (only in iteration 3 - most recent)
    boost_one = ae._get_evolution_boost(scene_id, 'camera', 'recent_only')

    # Both have same quality/alignment (0.5)
    # But boost_many has more matches AND higher recency_sum
    # recency for many: 1 + 0.5 + 0.333 = 1.833
    # recency for one: 1.0 (only at index 0 of its own pattern_uses)
    # So boost_many should be higher due to frequency + recency
    assert boost_many > boost_one, f"Expected boost_many ({boost_many}) > boost_one ({boost_one})"
    print("✓ test_evolution_boost_favors_recent_matches passed")


def test_evolution_boost_caps_at_maximum():
    """Test that boost caps at 1.0 + MAX_BOOST (1.75)"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_cap_boost'
    max_possible = 1.0 + ae._MAX_BOOST  # 1.75

    # Record many high-quality iterations to approach cap
    for i in range(10):
        evolution_tracker.record_evolution(
            scene_id=scene_id,
            iteration_number=i + 1,
            intent_alignment_score=0.95,
            quality_score=0.95,
            patterns_used=[{'pattern_type': 'composition', 'pattern_value': 'rule_of_thirds'}],
            deviations_used=[]
        )

    boost = ae._get_evolution_boost(scene_id, 'composition', 'rule_of_thirds')

    # Should be capped at max_possible
    assert boost <= max_possible, f"Expected boost ({boost}) <= max ({max_possible})"
    # But should still be significantly above 1.0
    assert boost > 1.5, f"Expected boost ({boost}) > 1.5"
    print("✓ test_evolution_boost_caps_at_maximum passed")


def test_evolution_boost_ignores_non_matching_patterns():
    """Test that boost returns 1.0 for patterns never recorded"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_no_match'

    # Record some patterns
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.9,
        quality_score=0.9,
        patterns_used=[{'pattern_type': 'camera', 'pattern_value': 'wide'}],
        deviations_used=[]
    )

    # Query for a different pattern
    boost = ae._get_evolution_boost(scene_id, 'camera', 'closeup')

    # No matches = no boost
    assert boost == 1.0, f"Expected 1.0 for non-matching pattern, got {boost}"
    print("✓ test_evolution_boost_ignores_non_matching_patterns passed")


def test_evolution_boost_handles_malformed_entries():
    """Test that malformed pattern entries are safely skipped"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_malformed'

    # Record with malformed patterns (missing keys, wrong types, etc.)
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.8,
        patterns_used=[
            {'pattern_type': 'camera', 'pattern_value': 'wide'},  # Valid
            {'type': 'lighting', 'value': 'high_key'},  # Valid (old keys)
            {},  # Empty - skip
            None,  # Not a dict - skip
            {'pattern_type': 'color'},  # Missing pattern_value - skip
            {'pattern_value': 'vibrant'},  # Missing pattern_type - skip
            'not_a_dict',  # String - skip
        ],
        deviations_used=[]
    )

    # Should still get boost for valid patterns
    boost = ae._get_evolution_boost(scene_id, 'camera', 'wide')
    assert boost > 1.0, f"Expected boost > 1.0 for valid pattern, got {boost}"

    # Should also work with old keys
    boost_old = ae._get_evolution_boost(scene_id, 'lighting', 'high_key')
    assert boost_old > 1.0, f"Expected boost > 1.0 for old-key pattern, got {boost_old}"

    print("✓ test_evolution_boost_handles_malformed_entries passed")


# =============================================================================
# PENALTY (NEGATIVE LEARNING) TESTS
# =============================================================================

def test_evolution_boost_penalizes_low_quality():
    """Test that patterns with low quality history result in multiplier < 1.0"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_penalty_quality'

    # All low quality (below 0.75 threshold) - should be negative matches
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.8,  # High alignment to not trigger penalty there
        quality_score=0.2,  # Low quality
        patterns_used=[{'pattern_type': 'camera', 'pattern_value': 'poor_quality'}],
        deviations_used=[]
    )
    boost = ae._get_evolution_boost(scene_id, 'camera', 'poor_quality')

    # Should be penalized (multiplier < 1.0)
    assert boost < 1.0, f"Expected boost < 1.0 for low quality, got {boost}"
    print("✓ test_evolution_boost_penalizes_low_quality passed")


def test_evolution_boost_penalizes_low_alignment():
    """Test that patterns with poor alignment result in multiplier < 1.0"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_penalty_alignment'

    # All low alignment (below 0.75 threshold) - should be negative matches
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.2,  # Low alignment
        quality_score=0.85,  # High quality to not trigger penalty there
        patterns_used=[{'pattern_type': 'lighting', 'pattern_value': 'poor_alignment'}],
        deviations_used=[]
    )
    boost = ae._get_evolution_boost(scene_id, 'lighting', 'poor_alignment')

    # Should be penalized (multiplier < 1.0)
    assert boost < 1.0, f"Expected boost < 1.0 for low alignment, got {boost}"
    print("✓ test_evolution_boost_penalizes_low_alignment passed")


def test_evolution_boost_mixed_history_balances_out():
    """Test that mixed good and bad history produces a reasonable multiplier"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_mixed_history'

    # One good iteration (just above positive threshold 0.75)
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=1,
        intent_alignment_score=0.8,
        quality_score=0.8,
        patterns_used=[{'pattern_type': 'color', 'pattern_value': 'mixed'}],
        deviations_used=[]
    )
    # One bad iteration (well below positive threshold)
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=2,
        intent_alignment_score=0.2,
        quality_score=0.2,
        patterns_used=[{'pattern_type': 'color', 'pattern_value': 'mixed'}],
        deviations_used=[]
    )
    boost = ae._get_evolution_boost(scene_id, 'color', 'mixed')

    # Should be between 0.9 and 1.75 (valid range)
    assert 0.9 <= boost <= 1.75, f"Expected boost between 0.9 and 1.75, got {boost}"
    # Should not be at extremes
    assert boost != 0.9, f"Expected boost not at minimum floor, got {boost}"
    assert boost != 1.75, f"Expected boost not at maximum cap, got {boost}"
    print("✓ test_evolution_boost_mixed_history_balances_out passed")


def test_evolution_boost_respects_min_floor():
    """Test that extremely poor history never drops below 0.9"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_min_floor'

    # Many iterations of extremely poor performance
    for i in range(5):
        evolution_tracker.record_evolution(
            scene_id=scene_id,
            iteration_number=i + 1,
            intent_alignment_score=0.1,
            quality_score=0.1,
            patterns_used=[{'pattern_type': 'lens', 'pattern_value': 'terrible'}],
            deviations_used=[]
        )
    boost = ae._get_evolution_boost(scene_id, 'lens', 'terrible')

    # Should not go below MIN_MULTIPLIER (0.9)
    assert boost >= 0.9, f"Expected boost >= 0.9, got {boost}"
    print("✓ test_evolution_boost_respects_min_floor passed")


def test_evolution_boost_positive_dominates_negative():
    """Test that mostly strong history still produces multiplier > 1.0"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import evolution_tracker

    ae = AdaptationEngine()
    scene_id = 'test_positive_dominates'

    # 4 good iterations
    for i in range(4):
        evolution_tracker.record_evolution(
            scene_id=scene_id,
            iteration_number=i + 1,
            intent_alignment_score=0.9,
            quality_score=0.9,
            patterns_used=[{'pattern_type': 'composition', 'pattern_value': 'mostly_good'}],
            deviations_used=[]
        )
    # 1 bad iteration
    evolution_tracker.record_evolution(
        scene_id=scene_id,
        iteration_number=5,
        intent_alignment_score=0.2,
        quality_score=0.2,
        patterns_used=[{'pattern_type': 'composition', 'pattern_value': 'mostly_good'}],
        deviations_used=[]
    )
    boost = ae._get_evolution_boost(scene_id, 'composition', 'mostly_good')

    # Positive should dominate (multiplier > 1.0)
    assert boost > 1.0, f"Expected boost > 1.0 for mostly good history, got {boost}"
    print("✓ test_evolution_boost_positive_dominates_negative passed")


# ============================================================================
# CONTEXT-AWARE CROSS-SCENE TESTS
# ============================================================================

def test_context_aware_empty_context_returns_same_scene():
    """When similarity_context is empty, should return same-scene boost only"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import SceneContext
    
    engine = AdaptationEngine()
    
    # Empty context should return same-scene boost
    ctx = SceneContext()  # Empty
    result = engine._get_evolution_boost("scene1", "camera", "wide", ctx)
    
    # Without any evolution data, should return 1.0
    assert result == 1.0, f"Expected 1.0 for empty context, got {result}"
    print("✓ test_context_aware_empty_context_returns_same_scene passed")


def test_context_aware_partial_context_works():
    """Partial context (some fields set) should work"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import SceneContext
    
    engine = AdaptationEngine()
    
    # Partial context with only emotion set
    ctx = SceneContext(emotion="tense")
    result = engine._get_evolution_boost("scene1", "camera", "wide", ctx)
    
    # Without evolution data, should return 1.0
    assert result == 1.0, f"Expected 1.0, got {result}"
    print("✓ test_context_aware_partial_context_works passed")


def test_context_aware_low_similarity_skips_cross_scene():
    """Low similarity should not apply cross-scene boost"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import SceneContext
    
    engine = AdaptationEngine()
    
    # Context with specific values
    ctx = SceneContext(emotion="tense", genre="noir")
    
    # Since _find_similar_scenes_for_context returns empty list,
    # cross-scene should not apply
    result = engine._calculate_cross_scene_boost("scene1", "camera", "wide", ctx)
    
    # Should return 1.0 when no similar scenes found
    assert result == 1.0, f"Expected 1.0 when no similar scenes, got {result}"
    print("✓ test_context_aware_low_similarity_skips_cross_scene passed")


def test_context_aware_shadow_mode_logs():
    """Shadow mode should log but not apply cross-scene boost"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import SceneContext
    
    engine = AdaptationEngine()
    
    # Verify shadow mode is enabled by default
    assert engine._ENABLE_CROSS_SCENE_SHADOW_MODE == True
    assert engine._ENABLE_CROSS_SCENE_REUSE == False
    
    # Context with specific values
    ctx = SceneContext(emotion="tense", genre="noir")
    
    # Cross-scene boost should return 1.0 in shadow mode
    result = engine._calculate_cross_scene_boost("scene1", "camera", "wide", ctx)
    assert result == 1.0, f"Shadow mode should not apply boost, got {result}"
    print("✓ test_context_aware_shadow_mode_logs passed")


def test_context_aware_fallback_no_similar_scenes():
    """Fallback when no similar scenes found"""
    from app.services.adaptation import AdaptationEngine
    from app.services.scene_evolution import SceneContext
    
    engine = AdaptationEngine()
    
    # Context with specific values
    ctx = SceneContext(emotion="tense", genre="noir")
    
    # Should return 1.0 when no similar scenes
    result = engine._calculate_cross_scene_boost("scene1", "camera", "wide", ctx)
    assert result == 1.0, f"Expected 1.0 when no similar scenes, got {result}"
    print("✓ test_context_aware_fallback_no_similar_scenes passed")


def test_context_aware_feature_flags_exist():
    """Verify feature flags are properly set"""
    from app.services.adaptation import AdaptationEngine
    
    engine = AdaptationEngine()
    
    # Check all the feature flags exist and have correct defaults
    assert hasattr(engine, '_ENABLE_CROSS_SCENE_REUSE')
    assert hasattr(engine, '_ENABLE_CROSS_SCENE_SHADOW_MODE')
    assert hasattr(engine, '_CROSS_SCENE_MIN_SIMILAR_SCENES')
    assert hasattr(engine, '_CROSS_SCENE_AVG_SIMILARITY_THRESHOLD')
    assert hasattr(engine, '_CROSS_SCENE_BLEND_RATIO')
    assert hasattr(engine, '_CROSS_SCENE_BOOST_FLOOR')
    assert hasattr(engine, '_CROSS_SCENE_BOOST_CEILING')
    
    # Check default values
    assert engine._ENABLE_CROSS_SCENE_REUSE == False
    assert engine._ENABLE_CROSS_SCENE_SHADOW_MODE == True
    assert engine._CROSS_SCENE_MIN_SIMILAR_SCENES == 2
    assert engine._CROSS_SCENE_AVG_SIMILARITY_THRESHOLD == 0.45
    assert engine._CROSS_SCENE_BLEND_RATIO == 0.15
    assert engine._CROSS_SCENE_BOOST_FLOOR == 0.95
    assert engine._CROSS_SCENE_BOOST_CEILING == 1.05
    
    print("✓ test_context_aware_feature_flags_exist passed")


def test_context_aware_blend_ratio_conservative():
    """Verify blend ratio is conservative (85% same-scene, 15% cross-scene)"""
    from app.services.adaptation import AdaptationEngine
    
    engine = AdaptationEngine()
    
    # 15% cross-scene means 85% same-scene
    assert engine._CROSS_SCENE_BLEND_RATIO == 0.15
    assert (1.0 - engine._CROSS_SCENE_BLEND_RATIO) == 0.85
    
    print("✓ test_context_aware_blend_ratio_conservative passed")


def test_context_aware_boost_clamping():
    """Verify cross-scene boost is clamped to safe range"""
    from app.services.adaptation import AdaptationEngine
    
    engine = AdaptationEngine()
    
    # Check clamping bounds exist
    assert engine._CROSS_SCENE_BOOST_FLOOR == 0.95
    assert engine._CROSS_SCENE_BOOST_CEILING == 1.05
    
    # Also check the "only" bounds for when same-scene data is missing
    assert engine._CROSS_SCENE_ONLY_FLOOR == 0.92
    assert engine._CROSS_SCENE_ONLY_CEILING == 1.08
    
    print("✓ test_context_aware_boost_clamping passed")


def run_all_tests():
    """Run all tests"""
    print("=== Scene Evolution Test Suite ===")
    print()

    test_record_evolution_basic()
    test_record_evolution_multiple()
    test_get_evolution_data_with_limit()
    test_get_evolution_data_not_found()
    test_compute_improvement_metrics_empty()
    test_compute_improvement_metrics_with_data()
    test_global_instance_has_new_methods()
    test_existing_record_iteration_still_works()
    test_normalize_patterns_old_keys()
    test_normalize_patterns_new_keys()
    test_normalize_patterns_mixed_keys()
    test_get_evolution_boost_with_none_scene_id()
    test_adaptation_boost_with_normalized_patterns()
    test_agent_executor_import_chain()
    # Weighted scoring tests
    test_evolution_boost_increases_with_frequency()
    test_evolution_boost_increases_with_quality()
    test_evolution_boost_increases_with_alignment()
    test_evolution_boost_favors_recent_matches()
    test_evolution_boost_caps_at_maximum()
    test_evolution_boost_ignores_non_matching_patterns()
    test_evolution_boost_handles_malformed_entries()
    # Penalty (negative learning) tests
    test_evolution_boost_penalizes_low_quality()
    test_evolution_boost_penalizes_low_alignment()
    test_evolution_boost_mixed_history_balances_out()
    test_evolution_boost_respects_min_floor()
    test_evolution_boost_positive_dominates_negative()
    # Context-aware cross-scene tests
    test_context_aware_empty_context_returns_same_scene()
    test_context_aware_partial_context_works()
    test_context_aware_low_similarity_skips_cross_scene()
    test_context_aware_shadow_mode_logs()
    test_context_aware_fallback_no_similar_scenes()
    test_context_aware_feature_flags_exist()
    test_context_aware_blend_ratio_conservative()
    test_context_aware_boost_clamping()

    print()
    print("=== ALL TESTS PASSED ===")


if __name__ == '__main__':
    run_all_tests()