from golden_rates import validate_golden_canaries


def test_validate_golden_canaries_pass():
    catalog = {
        "models": [
            {
                "model_id": "amazon.nova-lite-v1:0",
                "on_demand": {"input_per_1m": 0.06, "output_per_1m": 0.24},
            }
        ]
    }
    failures = validate_golden_canaries(
        catalog,
        path=__import__("pathlib").Path(__file__).parent / "fixtures" / "golden_rates.json",
    )
    assert failures == [] or all("nova-micro" in f or "claude" in f for f in failures)
