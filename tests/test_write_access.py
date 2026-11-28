"""Write access to Desktop/Documents is opt-in: read-only unless .env says exactly 'rw'."""

from pathlib import Path

import yaml

from steward.config import AppConfig
from steward.path_mapper import PathMapper
from steward.settings_service import SettingsService
from steward.tools.tool_paths import ToolPaths


def docker_paths(tmp_path, monkeypatch, switch=None):
    """ToolPaths that pretends tmp/Desktop is the Docker mount /data/Desktop with its .env switch."""
    desktop = (tmp_path / "Desktop").resolve()
    desktop.mkdir(exist_ok=True)
    monkeypatch.setattr(ToolPaths, "ACCESS_VARS", {str(desktop): "STEWARD_DESKTOP_ACCESS"})
    env = {"STEWARD_DESKTOP_ACCESS": switch} if switch is not None else {}
    mapper = PathMapper(None, env=env, mappings=[("/Users/you/Desktop", str(desktop))])
    return ToolPaths(mapper), desktop


class TestAccessSwitch:
    """Docker accepts any mount mode except 'ro' as writable, so Steward checks the switch itself."""

    def test_unset_switch_means_read_only_with_the_fix(self, tmp_path, monkeypatch):
        """No switch: Steward refuses changes and names STEWARD_DESKTOP_ACCESS=rw."""
        paths, desktop = docker_paths(tmp_path, monkeypatch)
        assert paths.is_writable(desktop) is False
        try:
            paths.check_writable(str(desktop / "a.txt"))
            raise AssertionError("should be read-only")
        except ValueError as exc:
            assert "set STEWARD_DESKTOP_ACCESS=rw" in str(exc) and "/Users/you/Desktop" in str(exc)

    def test_only_exactly_rw_allows_changes(self, tmp_path, monkeypatch):
        """'rw' (any case, spaces trimmed) allows changes; 'yes' or 'false' never do."""
        for switch, expected in (("rw", True), (" RW ", True), ("ro", False), ("yes", False), ("false", False)):
            paths, desktop = docker_paths(tmp_path, monkeypatch, switch)
            assert paths.is_writable(desktop) is expected, switch

    def test_wrong_value_is_explained(self, tmp_path, monkeypatch):
        """A value other than rw/ro gets its own message, showing what was found."""
        paths, desktop = docker_paths(tmp_path, monkeypatch, "yes")
        message = paths._read_only_message(str(desktop))
        assert "must be 'rw' or 'ro' (found 'yes')" in message

    def test_outside_docker_the_switch_is_ignored(self, tmp_path):
        """Running directly on the Mac, normal file permissions decide."""
        paths = ToolPaths(PathMapper(None, env={}))
        assert paths.is_writable(tmp_path) is True


class TestSettingsAndPaths:
    """Settings shows read-only/writable per folder; Steward's own files show as Mac paths."""

    def test_settings_folders_report_writable(self, tmp_path, monkeypatch):
        """Each watched folder carries writable and the .env switch that controls it."""
        desktop = (tmp_path / "Desktop").resolve()
        desktop.mkdir()
        (tmp_path / "config.yaml").write_text(yaml.safe_dump({"scanner": {"watched_folders": [str(desktop)]}}))
        config = AppConfig(config_path=tmp_path / "config.yaml", base_dir=tmp_path)
        monkeypatch.setattr(ToolPaths, "ACCESS_VARS", {str(desktop): "STEWARD_DESKTOP_ACCESS"})
        for switch, expected in (("ro", False), ("rw", True)):
            mapper = PathMapper(config, env={"STEWARD_DESKTOP_ACCESS": switch}, mappings=[("/Users/you/Desktop", str(desktop))])
            folder = SettingsService(config, mapper, env={}).current()["folders"][0]
            assert folder["writable"] is expected and folder["access_var"] == "STEWARD_DESKTOP_ACCESS"

    def test_settings_show_protected_folders_and_override_file_as_mac_paths(self, tmp_path):
        """Protected folders and the override file are shown with the user's Mac paths."""
        (tmp_path / "config.yaml").write_text(yaml.safe_dump({"safety": {"protected_paths": ["/data/Desktop/Clients"]}}))
        config = AppConfig(config_path=tmp_path / "config.yaml", base_dir=tmp_path)
        mapper = PathMapper(config, env={"STEWARD_HOST_APP_DIR": "/Users/you/steward"},
                            mappings=[("/Users/you/Desktop", "/data/Desktop")])
        mapper.display_mappings.append(("/Users/you/steward/data", str(config.override_path().parent)))
        current = SettingsService(config, mapper, env={}).current()
        assert "/Users/you/Desktop/Clients" in current["safety"]["protected_paths"]
        assert current["override_file"] == "/Users/you/steward/data/settings.override.yaml"

    def test_steward_data_paths_show_as_mac_paths_but_are_not_scannable(self):
        """/app/data/... reads as the project folder; it is never offered as a folder to scan."""
        mapper = PathMapper(None, env={"STEWARD_HOST_APP_DIR": "/Users/you/steward"},
                            mappings=[("/Users/you/Desktop", "/data/Desktop")])
        text = mapper.to_host_deep("Saved to /app/data/archives/docs.zip, not /app/database")
        assert text == "Saved to /Users/you/steward/data/archives/docs.zip, not /app/database"
        assert mapper.to_container("/Users/you/steward/data/x") == "/Users/you/steward/data/x"
        assert [root["path"] for root in mapper.list_roots()] == ["/data/Desktop"]


class TestCompose:
    """docker-compose.yml keeps Desktop and Documents read-only unless .env opts in."""

    def test_mounts_default_to_read_only(self):
        """API and worker mount Desktop/Documents with the opt-in switch, defaulting to ro."""
        compose = yaml.safe_load((Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text())
        for service in ("steward-api", "steward-worker"):
            volumes = compose["services"][service]["volumes"]
            assert any(v.endswith(":/data/Desktop:${STEWARD_DESKTOP_ACCESS:-ro}") for v in volumes)
            assert any(v.endswith(":/data/Documents:${STEWARD_DOCUMENTS_ACCESS:-ro}") for v in volumes)
            assert "STEWARD_DESKTOP_ACCESS=${STEWARD_DESKTOP_ACCESS:-ro}" in compose["services"][service]["environment"]
