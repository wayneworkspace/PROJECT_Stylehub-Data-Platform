# Shortcuts for the project. Run from the project folder: make clean
# Windows: install GNU make once with: winget install ezwinports.make (then open a new terminal).
# make is optional: the clean target is one Python line, so you can run that line by hand instead.

.PHONY: clean

# Remove the files that the tools create by themselves. Git ignores all of them and they come back
# the next time you run the code.
#   folders: __pycache__ (Python), .ruff_cache, .mypy_cache, .pytest_cache,
#            dbt/target and dbt/logs (dbt build output)
#   files:   .coverage*, dbt/.user.yml
# It does NOT touch .venv, data/, secrets/ or logs/.
# It uses Python (not rm), so the same line works in PowerShell, cmd and bash.
clean:
	uv run --no-project python -c "import shutil, pathlib as p; [shutil.rmtree(d, ignore_errors=True) for d in [*p.Path('.').rglob('__pycache__'), *map(p.Path, ('.ruff_cache', '.mypy_cache', '.pytest_cache', 'dbt/target', 'dbt/logs'))] if '.venv' not in d.parts]; [f.unlink() for f in [*p.Path('.').glob('.coverage*'), p.Path('dbt/.user.yml')] if f.is_file()]; print('clean: done')"
