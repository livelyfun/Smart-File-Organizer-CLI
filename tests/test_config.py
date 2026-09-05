"""Unit tests for configuration loading and validation."""

import json
from pathlib import Path
import pytest

from smart_organizer.config import (
    AppConfig,
    load_config,
    save_config,
    validate_config_data,
)
from smart_organizer.platform_utils import get_config_dir, get_default_downloads_dir


def test_default_config():
    config = AppConfig()
    assert config.stability_delay == 2.0
    assert config.stability_checks == 2
    assert config.max_stability_wait == 60.0
    assert config.ignore_hidden_files is True
    assert ".crdownload" in config.temporary_extensions
    assert config.resolved_watch_directory == get_default_downloads_dir()


def test_config_save_and_load(tmp_path: Path):
    cfg_file = tmp_path / "custom_config.json"
    custom_cfg = AppConfig(
        watch_directory=str(tmp_path / "custom_downloads"),
        stability_delay=3.5,
        stability_checks=4,
        ignore_hidden_files=False,
        temporary_extensions=[".temp", ".part"],
        log_file=None,
        custom_categories={"Books": [".epub"]},
    )

    save_config(custom_cfg, cfg_file)
    loaded = load_config(config_path=cfg_file)

    assert loaded.watch_directory == str(tmp_path / "custom_downloads")
    assert loaded.stability_delay == 3.5
    assert loaded.stability_checks == 4
    assert loaded.ignore_hidden_files is False
    assert loaded.temporary_extensions == [".temp", ".part"]
    assert loaded.log_file is None
    assert loaded.custom_categories == {"Books": [".epub"]}


def test_config_cli_override(tmp_path: Path):
    cfg_file = tmp_path / "config.json"
    save_config(AppConfig(watch_directory="/base/path"), cfg_file)

    loaded = load_config(config_path=cfg_file, watch_dir_override="/override/path")
    assert loaded.watch_directory == "/override/path"


def test_config_validation_errors():
    with pytest.raises(ValueError, match="watch_directory"):
        validate_config_data({"watch_directory": ""})

    with pytest.raises(ValueError, match="stability_delay"):
        validate_config_data({"stability_delay": -1})

    with pytest.raises(ValueError, match="stability_checks"):
        validate_config_data({"stability_checks": 0})

    with pytest.raises(ValueError, match="max_stability_wait"):
        validate_config_data({"max_stability_wait": 0})

    with pytest.raises(ValueError, match="ignore_hidden_files"):
        validate_config_data({"ignore_hidden_files": "invalid"})

    with pytest.raises(ValueError, match="temporary_extensions"):
        validate_config_data({"temporary_extensions": "not_a_list"})

    with pytest.raises(ValueError, match="custom_categories"):
        validate_config_data({"custom_categories": "not_a_dict"})
