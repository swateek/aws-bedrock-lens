from normalize_rate import normalize_rate, normalize_token_rate


def test_normalize_1k_tokens():
    result = normalize_rate("1K tokens", 0.00006, metric_hint="input_tokens")
    assert result is not None
    assert result.rate_usd == 0.06
    assert result.catalog_field == "input_per_1m"


def test_normalize_1m_tokens_no_scale():
    result = normalize_rate("1M tokens", 1.25, metric_hint="output_tokens")
    assert result is not None
    assert result.rate_usd == 1.25
    assert result.catalog_field == "output_per_1m"


def test_normalize_fm_units_million_description():
    result = normalize_token_rate(
        "Units",
        3.0,
        description="AWS Marketplace software usage|us-east-1|Price per 1 million input tokens",
    )
    assert result is not None
    assert result.rate_usd == 3.0


def test_normalize_image_unit():
    result = normalize_rate("image", 0.04, metric_hint="image_standard")
    assert result is not None
    assert result.rate_usd == 0.04
    assert result.catalog_field == "standard_per_image"


def test_normalize_seconds():
    result = normalize_rate("seconds", 0.08, metric_hint="video_second")
    assert result is not None
    assert result.rate_usd == 0.08
    assert result.catalog_field == "per_second"
