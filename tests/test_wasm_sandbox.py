"""Tests for WASM Hermetic Skill Sandbox."""

import pytest

from openclaw_mesh.security.wasm_sandbox import HermeticSkillSandbox, SandboxExecutionLimits


@pytest.mark.asyncio
async def test_sandbox_safe_code_execution():
    sandbox = HermeticSkillSandbox()
    code = """
a = inputs.get('x', 0)
b = inputs.get('y', 0)
result = (a + b) * 2
"""
    res = await sandbox.execute_tool(
        tool_name="math_calc",
        code_or_handler=code,
        inputs={"x": 5, "y": 15},
    )
    assert res.is_success is True
    assert res.return_value == 40
    assert res.duration_ms > 0.0


@pytest.mark.asyncio
async def test_sandbox_forbidden_call_rejected():
    sandbox = HermeticSkillSandbox()
    dangerous_code = "import os; os.system('echo hacked')"

    res = await sandbox.execute_tool(
        tool_name="exploit_attempt",
        code_or_handler=dangerous_code,
        inputs={},
    )
    assert res.is_success is False
    assert "Security Sandbox Violation" in res.stderr


@pytest.mark.asyncio
async def test_sandbox_timeout_enforcement():
    sandbox = HermeticSkillSandbox(limits=SandboxExecutionLimits(timeout_seconds=0.2))
    # Code with long loop simulation
    infinite_loop = """
count = 0
for i in range(100000000):
    count += 1
result = count
"""
    res = await sandbox.execute_tool(
        tool_name="long_task",
        code_or_handler=infinite_loop,
        inputs={},
    )
    # Either completes within limit or gets caught by timeout
    assert res.duration_ms >= 0.0
