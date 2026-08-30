from __future__ import annotations

from html.parser import HTMLParser

from fastapi.testclient import TestClient

from app.main import create_app


class AppShellParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.header_text: list[str] = []
        self.tab_text: list[str] = []
        self.tab_panels: list[str] = []
        self.stylesheets: list[str] = []
        self.module_scripts: list[str] = []
        self.textareas: list[str] = []
        self.button_labels: dict[str, list[str]] = {}
        self._in_header = False
        self._in_tab = False
        self._button_id: str | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "header":
            self._in_header = True
        if tag == "button" and attributes.get("role") == "tab":
            self._in_tab = True
        if tag == "button" and attributes.get("id"):
            self._button_id = attributes["id"]
            self.button_labels[self._button_id] = []
        if tag == "textarea" and attributes.get("id"):
            self.textareas.append(attributes["id"])
        if attributes.get("role") == "tabpanel":
            self.tab_panels.append(attributes.get("id", ""))
        if tag == "link" and attributes.get("rel") == "stylesheet":
            self.stylesheets.append(attributes.get("href", ""))
        if tag == "script" and attributes.get("type") == "module":
            self.module_scripts.append(attributes.get("src", ""))

    def handle_endtag(self, tag):
        if tag == "header":
            self._in_header = False
        if tag == "button" and self._in_tab:
            self._in_tab = False
        if tag == "button":
            self._button_id = None

    def handle_data(self, data):
        text = data.strip()
        if text and self._in_header:
            self.header_text.append(text)
        if text and self._in_tab:
            self.tab_text.append(text)
        if text and self._button_id:
            self.button_labels[self._button_id].append(text)


def make_client(tmp_path) -> TestClient:
    return TestClient(
        create_app(
            data_root=tmp_path / "data",
            dataset_state_path=tmp_path / "dataset-state.json",
            provider_config_path=tmp_path / "provider.json",
            user_decks_path=tmp_path / "decks.json",
        )
    )


def test_root_serves_approved_companion_top_tab_shell(tmp_path):
    response = make_client(tmp_path).get("/")
    parser = AppShellParser()
    parser.feed(response.text)

    assert response.status_code == 200
    assert " ".join(parser.header_text) == "PTCG Deck Analysis"
    assert parser.tab_text == ["Analysis", "Deck Library", "AI Backend", "Tournament Reports"]
    assert parser.tab_panels == [
        "analysis-panel",
        "deck-library-panel",
        "ai-backend-panel",
        "tournament-reports-panel",
    ]
    assert parser.stylesheets == ["/static/styles.css"]
    assert parser.module_scripts == ["/static/app.js"]


def test_split_frontend_assets_are_served(tmp_path):
    client = make_client(tmp_path)

    stylesheet = client.get("/static/styles.css")
    application = client.get("/static/app.js")
    core = client.get("/static/core.mjs")
    reports = client.get("/static/tournament-reports.js")
    report_core = client.get("/static/tournament-reports-core.mjs")

    assert stylesheet.status_code == 200
    assert stylesheet.headers["content-type"].startswith("text/css")
    assert application.status_code == 200
    assert "javascript" in application.headers["content-type"]
    assert core.status_code == 200
    assert "javascript" in core.headers["content-type"]
    assert reports.status_code == 200
    assert "javascript" in reports.headers["content-type"]
    assert report_core.status_code == 200
    assert "javascript" in report_core.headers["content-type"]
    assert "./tournament-reports.js" in application.text


def test_tournament_report_routes_serve_the_application_shell(tmp_path):
    client = make_client(tmp_path)

    index = client.get("/tournament-reports")
    deep_link = client.get(
        "/tournament-reports/2026-new-orleans-ma/families/dragapult-ex"
    )

    assert index.status_code == 200
    assert deep_link.status_code == 200
    assert "tournament-reports-panel" in index.text
    assert deep_link.text == index.text


def test_deck_library_uses_one_full_list_textarea_instead_of_per_card_controls(tmp_path):
    response = make_client(tmp_path).get("/")
    parser = AppShellParser()
    parser.feed(response.text)

    assert parser.textareas == ["deck-input", "deck-library-input"]
    assert parser.button_labels["parse-library-deck-btn"] == ["Parse and validate"]
    assert parser.button_labels["save-deck-btn"] == ["Save deck"]
    assert not {"Add Pokémon", "Add Trainer", "Add Energy"}.intersection(
        text for labels in parser.button_labels.values() for text in labels
    )
