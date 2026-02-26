# tests/test_evolution.py
import pytest
from nanobot.meta.introspector import introspector
from nanobot.meta.planner import planner
from nanobot.db.engine import db

@pytest.fixture
async def setup_db(require_db):
    await db.execute("DELETE FROM reference_patterns WHERE source_repo = 'test_ref'")
    await db.execute("DELETE FROM system_model WHERE component_name = 'analyze_data'")
    await db.execute("DELETE FROM evolution_queue WHERE target_component = 'analyze_data'")
    yield

@pytest.mark.asyncio
async def test_evolution_gap_detection(tmp_path, setup_db):
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir()
    
    code = """
def analyze_data(dataset_path):
    '''Analyzes a dataset and returns stats.'''
    return "stats"
"""
    (ref_dir / "analytics.py").write_text(code)
    
    await introspector.scan_reference_repo(str(ref_dir), "test_ref")
    
    patterns = await db.fetch("SELECT * FROM reference_patterns WHERE source_repo = 'test_ref'")
    assert len(patterns) == 1
    assert patterns[0]['pattern_name'] == "analyze_data"
    
    proposals = await planner.identify_gaps()
    
    assert any(p['target'] == 'analyze_data' for p in proposals)

@pytest.mark.asyncio
async def test_evolution_execution(tmp_path, setup_db):
    await db.execute("""
        INSERT INTO reference_patterns (source_repo, pattern_name, pattern_type, definition)
        VALUES ('test_ref', 'dummy_feature', 'function', '{"name": "dummy_feature", "args": [], "docstring": "Test"}')
    """)
    
    proposals = await planner.identify_gaps()
    assert len(proposals) > 0
    
    prop = next(p for p in proposals if p['target'] == 'dummy_feature')
    
    from nanobot.meta.schemas import SkillDefinition
    skill_def = SkillDefinition(**prop['spec'])
    
    assert skill_def.name == "gen-dummy-feature"
    assert len(skill_def.tools) == 1
    assert skill_def.tools[0].name == "dummy_feature"
