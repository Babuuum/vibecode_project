from autocontent.services.draft_templates import render_prompt


def test_render_prompt_includes_template_and_facts() -> None:
    prompt = render_prompt(
        template_id="digest",
        facts="Fact A",
        link="http://example.com/1",
        language="en",
        tone="formal",
        niche="tech",
        max_post_len=200,
    )

    assert "Template: digest" in prompt
    assert "Fact A" in prompt
    assert "Keep under 200 chars." in prompt
