from minutes import tasks


def test_worker_prompt_includes_language_and_actions():
    prompt = tasks.build_system_prompt(
        {"language": "Japanese", "include_actions": False}
    )

    assert prompt is not None
    assert "日本語" in prompt or "Japanese" in prompt
    assert "Do not extract action items" in prompt
