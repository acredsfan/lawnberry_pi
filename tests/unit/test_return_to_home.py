from backend.src.scheduler.return_to_home import ReturnToHome


def test_return_to_home_action_shape():
    rth = ReturnToHome()
    action = rth.make_action()
    assert action["type"] == "navigate"
    assert action["target_waypoint_type"] == "home"
    assert isinstance(action["metadata"], dict)
