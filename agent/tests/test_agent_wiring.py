from heat_planner.agent import root_agent


def test_root_agent_routes_to_one_specialist_per_job():
    names = {a.name for a in root_agent.sub_agents}
    assert names == {"prediction_analyst", "siting_analyst", "planting_analyst", "history_analyst", "community_analyst"}


def test_every_specialist_has_tools_and_a_description():
    for agent in root_agent.sub_agents:
        assert agent.tools and agent.description


def test_prediction_agent_owns_the_model_tools():
    agent = next(a for a in root_agent.sub_agents if a.name == "prediction_analyst")
    assert {t.__name__ for t in agent.tools} == {"predict_heat_offset", "rank_response_sites"}


def test_each_track_has_its_own_specialist_and_tool():
    by_name = {a.name: {t.__name__ for t in a.tools} for a in root_agent.sub_agents}
    assert by_name["siting_analyst"] == {"recommend_cooling_centers"}
    assert by_name["planting_analyst"] == {"rank_planting_sites"}


def test_the_selected_track_is_in_the_root_instruction():
    from heat_planner import prompts

    assert "BUDGET CYCLE track" in prompts.root("Dallas", "budget").replace("budget cycle", "BUDGET CYCLE")
    assert "THIS DECADE track" in prompts.root("Dallas", "trees")
    assert "working on the" not in prompts.root("Dallas", None)
    assert "latitude and longitude" in prompts.ROOT  # tells the model never to ask for them


def test_gemini_4_gets_a_low_thinking_planner_and_other_models_do_not():
    from heat_planner.sub_agents import thinking_planner

    planner = thinking_planner("gemini-4-argon")
    assert planner is not None and str(planner.thinking_config.thinking_level).upper().endswith("LOW")
    assert thinking_planner("gemini-2.5-flash") is None
