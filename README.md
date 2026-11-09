# Dataset Steward

Tools to validate and describe `ds-*` dataset folders. Each dataset's `README.md` is generated from its `datapackage.json` and `buckets.csv`.

## Contents

| File | Purpose |
| --- | --- |
| `validate.py` | Checks datasets, counts resource sizes and writes READMEs |
| `server.py`, `static/` | Local web page to view and edit datasets |
| `rules.json` | Allowed stages and the root items that don't need describing |
| `buckets.ipynb` | Example of how to create a `buckets.csv` |
| `test_validate.py` | Tests for the validator |

## Usage

```sh
python server.py                 # open http://127.0.0.1:8765/
python validate.py               # all ds-* folders next to _describe/
python validate.py ../ds-name    # one dataset
python validate.py --check       # validate without writing any files
```

Both accept `--input DIR` to use another folder of datasets. `server.py` needs `pip install markdown`, and runs the validator on startup.

Running either tool, except with `--check`, updates each resource's `size` in `datapackage.json`, and rewrites the README of each dataset that passes. In a README, text below `<!-- notes -->` is kept and everything above it is replaced.

## What a dataset needs

- `name`, `title` and `description`.
- `keywords`: exactly `task:<any>`, `project:<any>` and `stage:<master|curated|annotated|ground-truth>`, and no others. A folder ending in `-atd` must be `annotated`, and one ending in `-gt` must be `ground-truth`.
- `created`, in the form `2026-10-26T00:00:00Z`.
- `contributors`, each with a `title`.
- `resources`, with a `name`, `title` and `path` for every root file and folder, except those listed in `rules.json`.
- `buckets.csv`, as described below.
- `sources` are optional. Each one listed needs a `title`.

## Writing descriptions

Describe what the numbers can't capture, such as why the dataset exists, how it was made and what to watch out for.

Don't describe spread, size or people. These belong in `buckets.csv`, `size` and `contributors`.

## Buckets

`buckets.csv` holds the metadata that matters most for the dataset's task, such as spread (pages per year), error types (count per type) or agreement scores (percent per metric). Choose whatever fits the task.

The format is an index column, then a label column, then one or more numeric columns. `DataFrame.to_csv()` writes the index for you. See `buckets.ipynb` for an example.

## Sizes

Sizes are counted automatically on every run, so don't edit them by hand.

| Resource | `size` counts |
| --- | --- |
| `.csv` | Rows, not counting the header |
| `.json` | Top-level items |
| Folder | Files at any depth, not counting hidden files |
| Anything else | No size |
