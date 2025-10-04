from backend.src.scheduler.safety_validator import SafetyValidator


def test_pre_job_safety_validator_passes_when_all_clear():
    validator = SafetyValidator()

    def get_estop():
        return False

    def get_interlocks():
        return []

    def get_gps_ok():
        return True

    result = validator.validate_pre_job(
        estop_engaged=get_estop,
        active_interlocks=get_interlocks,
        gps_available=get_gps_ok,
    )

    assert result.ok is True
    assert result.reason is None


def test_pre_job_safety_validator_blocks_on_estop():
    validator = SafetyValidator()
    result = validator.validate_pre_job(
        estop_engaged=lambda: True,
        active_interlocks=lambda: [],
        gps_available=lambda: True,
    )
    assert result.ok is False
    assert "E-stop" in (result.reason or "")


def test_pre_job_safety_validator_blocks_on_interlocks():
    validator = SafetyValidator()
    result = validator.validate_pre_job(
        estop_engaged=lambda: False,
        active_interlocks=lambda: ["low_battery"],
        gps_available=lambda: True,
    )
    assert result.ok is False
    assert "interlocks" in (result.reason or "")


def test_pre_job_safety_validator_blocks_on_gps_unavailable():
    validator = SafetyValidator()
    result = validator.validate_pre_job(
        estop_engaged=lambda: False,
        active_interlocks=lambda: [],
        gps_available=lambda: False,
    )
    assert result.ok is False
    assert "GPS" in (result.reason or "")
