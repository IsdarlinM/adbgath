from __future__ import annotations

from adbgath.cli import build_parser, normalize_legacy_args


def test_legacy_list_translation():
    translated = normalize_legacy_args(["--device", "emulator-5554", "-l", "users"])
    assert translated == ["--device", "emulator-5554", "list", "users"]
    args = build_parser().parse_args(translated)
    assert args.command == "list"
    assert args.kind == "users"


def test_legacy_install_translation():
    translated = normalize_legacy_args(["--device", "emulator-5554", "--user", "0", "-I", "app.apk"])
    args = build_parser().parse_args(translated)
    assert args.command == "install"
    assert args.files == ["app.apk"]


def test_modern_parser():
    args = build_parser().parse_args(["--device", "serial", "logs", "capture", "--duration", "10"])
    assert args.command == "logs"
    assert args.duration == 10


def test_file_input_and_profile_alias(tmp_path):
    input_file = tmp_path / "packages.txt"
    input_file.write_text("# comment\ncom.example.one\ncom.example.two\n", encoding="utf-8")
    args = build_parser().parse_args(
        ["--device", "serial", "--profile", "current", "uninstall", "--file", str(input_file)]
    )
    assert args.command == "uninstall"
    assert args.user == "current"
    assert args.input_file == str(input_file)


def test_replace_file_and_logcat_legacy_filters_parse(tmp_path):
    replacements = tmp_path / "replacements.txt"
    replacements.write_text('"C:/APK files/app.apk" com.example.app\n', encoding="utf-8")
    replace_args = build_parser().parse_args(
        ["--device", "serial", "--user", "0", "replace", "--file", str(replacements)]
    )
    assert replace_args.command == "replace"
    assert replace_args.input_file == str(replacements)

    log_args = build_parser().parse_args(["logs", "capture", "--grep", "exception", "--filter", "*:W", "--clear-logs"])
    assert log_args.regex == "exception"
    assert log_args.filters == ["*:W"]
    assert log_args.clear_first is True


def test_all_cli_command_help_parses():
    parser = build_parser()
    commands = [
        ["devices"],
        ["connect", "127.0.0.1:5555"],
        ["disconnect", "127.0.0.1:5555"],
        ["list", "users"],
        ["download"],
        ["install"],
        ["uninstall"],
        ["replace"],
        ["info"],
        ["app", "com.example.app"],
        ["runtime"],
        ["logs"],
        ["sniff", "interfaces"],
        ["proxy", "show"],
        ["forward", "forward", "8080", "8080"],
        ["backup", "com.example.app"],
        ["content"],
        ["frida"],
        ["static", "app.apk"],
        ["install-set", "splits"],
        ["bundle", "inspect", "app.apks"],
        ["evidence"],
        ["assess", "com.example.app"],
        ["snapshot", "list"],
        ["project", "list"],
        ["findings"],
        ["group", "list"],
        ["run-group", "lab", "inventory"],
        ["plugin", "list"],
        ["report", "prj_example"],
        ["update", "check"],
        ["security"],
        ["collect"],
        ["mastg"],
        ["inventory"],
        ["doctor"],
        ["web"],
    ]
    for argv in commands:
        parsed = parser.parse_args(argv)
        assert parsed.command is not None
