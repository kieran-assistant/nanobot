# tests/test_meta_core.py
import pytest
from nanobot.meta.schemas import SkillDefinition, ToolDefinition, ParameterSchema, ExecutorType
from nanobot.meta.factory import factory
from nanobot.runtime.sandbox import sandbox
from nanobot.meta.staging_manager import staging_manager
from pathlib import Path
import json
import shutil

@pytest.mark.asyncio
async def test_factory_generation(tmp_path):
    tool_def = ToolDefinition(
        name="hello_world",
        description="Says hello",
        parameters=[ParameterSchema(name="name", type="string", description="Name to greet")],
        executor_type=ExecutorType.SCRIPT,
        executor_config={"command": "echo Hello"}
    )
    
    file_path = factory.generate_tool_script(tool_def, tmp_path)
    assert file_path.exists()
    content = file_path.read_text()
    assert "def execute(name=None)" in content

@pytest.mark.asyncio
async def test_sandbox_execution(tmp_path):
    tool_def = ToolDefinition(
        name="echo_test",
        description="Echoes input",
        executor_type=ExecutorType.SCRIPT,
        executor_config={"command": "echo test"}
    )
    script_path = factory.generate_tool_script(tool_def, tmp_path)
    
    result = await sandbox.execute_script(str(script_path), {})
    
    assert result['success'] is True
    assert "test" in result['data']['output']

@pytest.mark.asyncio
async def test_staging_lifecycle():
    skill_def = SkillDefinition(
        name="test_skill",
        description="A test skill",
        tools=[
            ToolDefinition(
                name="dummy_tool",
                description="Does nothing",
                executor_type=ExecutorType.SCRIPT,
                executor_config={"command": "ls"}
            )
        ]
    )
    
    result = await staging_manager.propose_skill(skill_def)
    
    assert result['status'] == 'deployed'
    
    expected_path = Path("nanobot/skills/test_skill")
    assert expected_path.exists()
    
    if expected_path.exists():
        shutil.rmtree(expected_path)
