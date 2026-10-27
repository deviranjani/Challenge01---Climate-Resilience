from heat_planner import config


def test_defaults_match_the_documented_models_and_locations(monkeypatch):
    for name in ("HEAT_AGENT_MODEL", "HEAT_ROUTER_MODEL", "HEAT_THINKING_LEVEL", "HEAT_LIVE_MODEL", "HEAT_LIVE_LOCATION",
                 "NWS_USER_AGENT", "BQML_MODEL_TYPE", "BQ_DATASET", "BQML_MODEL", "HEAT_CITY"):
        monkeypatch.delenv(name, raising=False)
    s = config.load_settings()
    assert s.llm_model == "gemini-4-argon" and s.router_model == "gemini-3.8-flash"
    assert s.thinking_level == "LOW"
    assert s.live_model == "gemini-live-2.5-flash-native-audio" and s.live_location == "us-central1"
    assert s.dataset == "a4i_climate" and s.model_name == "offset_model" and s.city == "Dallas"
    assert "HeatPlanner" in s.nws_user_agent and "LINEAR_REG" in s.bqml_type
    assert s.project_id == "test-project"  # set by the autouse fixture


def test_environment_overrides_every_model_setting(monkeypatch):
    monkeypatch.setenv("HEAT_AGENT_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("HEAT_ROUTER_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("HEAT_THINKING_LEVEL", "")
    monkeypatch.setenv("HEAT_LIVE_LOCATION", "us-east4")
    monkeypatch.setenv("NWS_USER_AGENT", "Team/1.0 (a@example.com)")
    s = config.load_settings()
    assert (s.llm_model, s.router_model, s.thinking_level, s.live_location) == ("gemini-2.5-flash", "gemini-2.5-flash", "", "us-east4")
    assert s.nws_user_agent == "Team/1.0 (a@example.com)"
