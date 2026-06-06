# Contributing to ADB APK Gatherer

Thank you for your interest in contributing to ADB APK Gatherer! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful and inclusive. Treat all contributors with courtesy and professionalism.

## Ways to Contribute

1. **Report Bugs** - Open an issue with a clear description
2. **Suggest Enhancements** - Share your ideas for improvements
3. **Submit Pull Requests** - Contribute code improvements
4. **Improve Documentation** - Help others understand how to use the tool

## Getting Started

### Prerequisites
- Bash 4.0+
- ADB installed
- Git

### Development Setup
```bash
git clone https://github.com/yourusername/adbgath.git
cd adbgath
chmod +x adbgath.sh
```

### Testing Changes
```bash
# Run with verbose mode
./adbgath.sh --verbose -d

# Test with different options
./adbgath.sh -l packages
./adbgath.sh --help
```

## Code Style Guidelines

### Bash Style
- Use `local` variables in functions
- Quote all variable references: `"$var"` not `$var`
- Use `[[ ]]` instead of `[ ]` for conditionals
- Use `readonly` for constants
- Use 4 spaces for indentation
- Add comments for complex logic

### Example
```bash
# Function description
function_name() {
    local var="value"
    local result
    
    # Comment explaining logic
    if [[ condition ]]; then
        result="something"
    fi
    
    echo "$result"
}
```

### Comments
```bash
################################################################################
# Section headers for major code blocks
################################################################################

# Function descriptions before function definition
# Explains what function does, parameters, return value

local_var="value"  # Inline comment for complex assignments
```

## Commit Guidelines

- Write clear, descriptive commit messages
- Use imperative mood: "Add feature" not "Added feature"
- Reference issues: "Fixes #123"
- Keep commits logical and atomic

Example:
```
Add verbose mode for debugging

- Implement --verbose flag
- Add debug() utility function
- Update help text
- Fixes #42
```

## Pull Request Process

1. **Fork** the repository
2. **Create** a branch for your feature: `git checkout -b feature/amazing-feature`
3. **Commit** your changes with clear messages
4. **Push** to your fork: `git push origin feature/amazing-feature`
5. **Open** a Pull Request with:
   - Clear title describing changes
   - Description of what and why
   - Reference to related issues
   - Test results if applicable

## Testing Checklist

Before submitting a PR, ensure:

- [ ] Script runs without errors
- [ ] No shellcheck warnings: `shellcheck adbgath.sh`
- [ ] All functions have proper error handling
- [ ] Help text is up to date
- [ ] Verbose mode works: `./adbgath.sh --verbose -l packages`
- [ ] Device connectivity validation works
- [ ] All exit codes are appropriate

## Reporting Bugs

When reporting bugs, include:

1. **System Information**
   ```
   OS: Linux/macOS/Windows (WSL)
   Bash version: $(bash --version)
   ADB version: $(adb version)
   ```

2. **Steps to Reproduce**
   ```
   1. Connect device
   2. Run: ./adbgath.sh -d
   3. Error occurs: ...
   ```

3. **Expected vs Actual Behavior**
4. **Relevant Output/Logs**
   ```
   ./adbgath.sh --verbose -d
   [output here]
   ```

## Feature Requests

Describe your idea:
- **Use Case**: What problem does it solve?
- **Implementation**: How might it work?
- **Example**: Show usage

## Documentation

- Update README.md for user-facing changes
- Update comments and function headers for code changes
- Keep CHANGELOG entries
- Use clear, simple English

## Questions?

Feel free to open an issue for questions or discussions!

## Recognition

All contributors will be recognized in the project's contributor list.

Thank you for making ADB APK Gatherer better! 🎉
