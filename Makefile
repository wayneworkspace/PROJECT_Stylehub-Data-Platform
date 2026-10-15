# Shortcuts for the project. Run from the project folder: make clean
# Windows: install GNU make first, once: winget install ezwinports.make (then open a new terminal).

.PHONY: clean

# Remove files that the tools create by themselves. Git ignores all of them and they come back
# when you run the code again. It does not touch .venv, .idea, data/, secrets/ or logs/.
# It uses Python (not rm), so the same line works in PowerShell, cmd and bash.
clean:
	uv run --no-project python -c "import shutil, pathlib as p; [shutil.rmtree(d, ignore_errors=True) for r in ('src', 'dbt', 'deploy', 'dev') for d in list(p.Path(r).rglob('__pycache__'))]; [shutil.rmtree(d, ignore_errors=True) for d in ('.ruff_cache', '.pytest_cache', 'dbt/target', 'dbt/logs')]"
