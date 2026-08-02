from mentat_broker.runtime import MentatV1Runtime


def test_runtime_exposes_release_spend_execution_and_recovery_state(tmp_path):
    runtime = MentatV1Runtime(tmp_path)
    try:
        status = runtime.status()
        assert status["target_version"] == "1.0.0"
        assert status["release"]["production_ready"] is False
        assert status["paid_compute_kill_switch"] is False
        runtime.set_kill_switch(True, reason="test", actor="pytest")
        assert runtime.status()["paid_compute_kill_switch"] is True
        analysis = runtime.analyze_task(
            "Fix this repository bug",
            tool_names=["git"],
        )
        assert analysis["task_class"] == "code"
    finally:
        runtime.close()
