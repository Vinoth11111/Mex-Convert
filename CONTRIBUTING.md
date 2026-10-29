# Contributing to Elumichai 🍋

Thanks for your interest in contributing! Elumichai is a free, offline file conversion tool for Linux. Every contribution, big or small, helps.

## Ways to Contribute

- **Report bugs**: a conversion failing or producing bad output? Open an issue.
- **Suggest features**: new formats, tools, or workflow ideas.
- **Improve docs**: fix typos, clarify steps, add examples.
- **Fix issues**: look for `good first issue` or `help wanted` labels.
- **Test on other distros**: we mainly target Debian 12 / Ubuntu, so reports from Fedora, Arch, and others are very welcome.

## Getting Started

1. **Fork** the repo and clone your fork:
   ```bash
   git clone https://github.com/<your-username>/Mex-Convert.git
   cd Mex-Convert
   ```
2. **Install dependencies** by following the [Manual Install](README.md#manual-install) steps in the README. A virtual environment is recommended:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```
3. **Verify your setup:**
   ```bash
   elumichai-cli check-deps
   ```

## Making Changes

1. Create a branch from `main` using a prefix like `fix/`, `feat/`, or `docs/`:
   ```bash
   git checkout -b fix/short-description
   ```
2. Keep each pull request focused on one change.
3. Test your changes (see below).
4. Commit with a clear message, for example `Fix HEIC to PNG conversion for large files`.
5. Push your branch and open a pull request against `main`.

## Testing

There's no automated test suite yet, so please test manually before opening a PR:

- Launch the app: `elumichai`
- Run the CLI command for the area you changed, for example:
  ```bash
  elumichai-cli convert sample.heic png
  elumichai-cli formats
  ```
- Try the specific conversion or tool you modified with a real file.
- Make sure other formats and tools still work.

## Code Style

- Python 3.9+ compatible, following [PEP 8](https://peps.python.org/pep-0008/).
- Clear names, small focused functions, comments for anything non-obvious.
- Don't commit generated files, build artifacts, or `*.egg-info` folders.

## Adding a New Format or Tool

1. Confirm the underlying program (FFmpeg, ImageMagick, Pandoc, etc.) supports it.
2. Add it to the relevant module in the package directory.
3. Make sure it works from both the GUI wheel and the CLI where applicable.
4. Update the **Supported Formats** or **Built-in Tools** table in the README.

## Pull Requests

Please include:

- **What** the change does and **why**
- The issue it fixes, if any (for example, `Fixes #12`)
- How you tested it, and on which OS and display server (X11 or Wayland)
- A screenshot or short clip for any UI change

Small, focused PRs get reviewed and merged fastest.

## Reporting Bugs

Please include:

- OS and version (for example, Ubuntu 24.04) and X11 or Wayland
- Python version (`python3 --version`)
- Steps to reproduce, with input and output formats
- The full error message or terminal output
- Output of `elumichai-cli check-deps`

## Good to Know

- The global drag ring uses X11. Wayland blocks global drag interception, so Wayland integration is a great area to contribute.
- Everything must stay **offline and local**. Please don't add features that upload user files.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

## Code of Conduct

Be kind and respectful. This should be a welcoming space for everyone, regardless of experience level. Harassment or discrimination won't be tolerated.

Thank you for helping make Elumichai better! 🍋