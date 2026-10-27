from heat_planner.agent import root_agent


def test_root_agent_routes_to_three_specialists():
    names = {a.name for a in root_agent.sub_agents}
    assert names == {"prediction_analyst", "history_analyst", "community_analyst"}


def test_every_specialist_has_tools_and_a_description():
    for agent in root_agent.sub_agents:
        assert agent.tools and agent.description


def test_prediction_agent_owns_the_model_tools():
    agent = next(a for a in root_agent.sub_agents if a.name == "prediction_analyst")
    assert {t.__name__ for t in agent.tools} == {"predict_heat_offset", "rank_response_sites"}
