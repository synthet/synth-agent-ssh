from synth_agent_ssh import hello


def test_hello() -> None:
    assert hello() == "hello from synth-agent-ssh"
