from app.settings import Settings
from app.utils import as_mcp_text


def test_settings_parsing_trims_url_and_allowlist():
    settings = Settings(
        MCP_API_KEY="secret",
        N8N_BASE_URL="https://example.com/",
        N8N_API_KEY="token",
        N8N_WORKFLOW_ALLOWLIST="100, 200 , ,",
    )
    assert settings.n8n_base_url == "https://example.com"
    assert settings.n8n_workflow_allowlist == {"100", "200"}


def test_as_mcp_text_wraps_content():
    result = as_mcp_text("hello")
    assert result.content[0].text == "hello"
    assert result.content[0].type == "text"
