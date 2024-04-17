# General

- All changes should be made through pull requests
- Pull requests should only be merged once all checks pass
- The repo uses Black for formatting Python code, Prettier for formatting Markdown,
  Pyright for type-checking Python, and a few other tools
- To generate reference documentation, follow the instructions in
  docs/generate_api_reference.py
- To run the CI checks locally:
  - `pip install pre-commit`
  - `pre-commit run --all` (or `pre-commit install` to install the pre-commit hook)

# Releases

To release a new version of `fastapi_poe`, do the following:

- Make a PR updating the version number in `pyproject.toml` (example:
  https://github.com/poe-platform/fastapi_poe/pull/2)
- Merge it once CI passes
- Go to https://github.com/poe-platform/fastapi_poe/releases/new and make a new release
  (note this link works only if you have commit access to this repository)
- The tag should be of the form "0.0.X".
- Fill in the release notes with some description of what changed since the last
  release.
- [GitHub Actions](https://github.com/poe-platform/fastapi_poe/actions) will generate
  the release artefacts and upload them to PyPI
- You can check [PyPI](https://pypi.org/project/fastapi-poe/) to verify that the release
  went through.
