from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def test_env_example_has_no_real_key_markers() -> None:
    content = (_project_root() / ".env.example").read_text(encoding="utf-8")
    lowered = content.lower()
    assert "sk-" not in lowered
    assert "bce-v3/" not in lowered


def test_env_example_defaults_are_provider_neutral() -> None:
    content = (_project_root() / ".env.example").read_text(encoding="utf-8")
    lines = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in content.splitlines()
        if line and not line.startswith("#") and "=" in line
    }
    assert lines.get("LLM_PROVIDER") == "mock"
    assert lines.get("SEARCH_PROVIDER") == "public_sources"
    assert lines.get("EMBEDDING_PROVIDER") == "local_hashing"
    assert lines.get("VECTOR_STORE") == "in_memory"
    assert lines.get("WORKFLOW_ENGINE") == "langgraph"


def test_env_example_api_key_fields_are_empty() -> None:
    content = (_project_root() / ".env.example").read_text(encoding="utf-8")
    key_lines = [line for line in content.splitlines() if line.endswith("API_KEY=")]
    assert key_lines, "应至少包含 API_KEY 占位字段"
    assert all(line.strip().endswith("API_KEY=") for line in key_lines)


def test_env_providers_example_can_include_vendor_names_but_keys_must_be_blank_or_commented() -> None:
    content = (_project_root() / ".env.providers.example").read_text(encoding="utf-8")
    lowered = content.lower()
    assert "deepseek" in lowered
    assert "baidu_ai_search" in lowered
    assert "dashscope" in lowered
    assert "siliconflow" in lowered
    assert "qianfan" in lowered

    for line in content.splitlines():
        raw = line.strip()
        if "API_KEY=" not in raw:
            continue
        # provider 模板里允许出现 API_KEY，但必须是注释行，且值为空
        assert raw.startswith("#"), f"provider 示例中的 key 必须注释：{line}"
        assert raw.endswith("API_KEY="), f"provider 示例中的 key 不能带值：{line}"
