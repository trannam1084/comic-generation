# Safe output behavior for optional dataset utilities

The corpus-preparation utilities read optional local candidate/review files. They must not silently replace curated metadata or old review artifacts.

## Default behavior

- `data/evaluate_stories.py` refuses to replace `data/metadata/ai_evaluated_stories.csv` when it already exists. Use `--output <new-path>` to create a separate output.
- `data/save_ai_review.py` refuses to replace either `ai_evaluated_stories.csv` or `selected_stories.csv` when either exists. Use `--output <path>` and `--selected-output <path>` to choose new destinations.
- `data/prepare_ai_review.py` refuses to replace any batch file that would be generated in the target directory. Use `--output-dir <new-directory>` to keep a new batch run separate.
- Existing targets can be replaced only with an explicit `--overwrite` flag. Take a backup first and inspect the output diff before doing this.

All targets are preflighted before writing. Text outputs are written through a same-directory temporary file and committed atomically. No script deletes other files in an output directory.

## Examples

```powershell
# Generate a new batch folder without overwriting old batches
python data/prepare_ai_review.py --output-dir data/metadata/ai_review_batches_run_02

# Save an AI experiment separately from curated metadata
python data/evaluate_stories.py --output data/metadata/ai_evaluated_stories_experiment.csv

# Merge review JSON into separate files
python data/save_ai_review.py --output data/metadata/ai_evaluated_stories_run_02.csv --selected-output data/metadata/selected_stories_run_02.csv

# Intentional replacement (only after backup and inspection)
python data/save_ai_review.py --overwrite
```

`--overwrite` is explicit and applies only to the output paths selected for that invocation; it does not delete other files or directories.
