# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Explicit Android user/profile targeting with `--user`, `--profile`, or `-u`.
- Device-root relevance marks in device listings: green `r` for rooted/relevant and yellow `i` for non-rooted/irrelevant.
- `logs`/`logcat` command for live log listening, file capture, package/PID filtering, regex filtering, buffer clearing, and timed capture.
- `sniff`/`pcap` command for rooted tcpdump-based network captures and interface listing.
- `collect` command wiring with metadata, root status, selected profile, and logcat snapshot output.
- New modular libraries for help, list, info, logs, and network capture.

### Changed
- Install, uninstall, and replace now require an explicit device and Android user/profile.
- Read-only device-targeted commands auto-select a device only when exactly one device is connected.
- Package and APK-path listing can be scoped to a selected Android user/profile.
- Help, README, quickstart, examples, and configuration docs now describe all current commands and targeting requirements.

### Planned Features
- Parallel downloads with GNU Parallel
- Filter by app type (system/user)
- Export APK list to JSON
- Resume interrupted downloads
- Batch operations
- Configuration file support

## [1.0.0] - 2026-06-06

### Added
- Initial release
- Download all APKs from connected device
- Download specific APKs by path
- Download APKs from file list
- List installed packages
- List APK paths
- Progress bar with file size information
- Verbose/debug mode with --verbose flag
- Linux-style command-line arguments (-d, --download, -l, --list, etc.)
- Comprehensive error handling and validation
- Device connectivity checking
- ADB dependency verification
- Color-coded output for better readability
- Help system with -h/--help
- Version display with -v/--version
- Code modularity with utility functions
- Proper exit codes for error conditions
- Shell script header with metadata and documentation
- Cleanup function with trap handling

### Technical Improvements
- Proper error handling with `set -euo pipefail`
- Quoted variable references to prevent word splitting
- Use of readonly for constants
- Local variables in functions
- DRY principle applied to download logic
- Logging functions (error, warning, info, success, debug)
- Dependency checking before execution
- Device validation before operations
- Comprehensive comments and documentation

### Documentation
- Comprehensive README.md with examples
- Contributing guidelines (CONTRIBUTING.md)
- MIT License
- Makefile for common tasks
- ShellCheck configuration
- This Changelog

---

## How to update this file

When making changes, follow these guidelines:

### Added
for new features

### Changed
for changes in existing functionality

### Deprecated
for soon-to-be removed features

### Removed
for now removed features

### Fixed
for any bug fixes

### Security
in case of vulnerabilities

---

## Release Process

1. Update version in script: `readonly VERSION="X.Y.Z"`
2. Update this CHANGELOG
3. Commit changes: `git commit -m "Release v1.0.0"`
4. Tag release: `git tag -a vX.Y.Z -m "Release version X.Y.Z"`
5. Push: `git push origin main --tags`
