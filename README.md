# Dataset Steward

Tools to validate and describe `ds-*` dataset folders. Each dataset's `README.md`
is generated from its `datapackage.json` and `buckets.csv`.

## Contents

| File | Purpose |
| --- | --- |
| `validate.py` | Checks datasets, counts resource items and writes READMEs |
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

Both accept `--input DIR` to use another folder of datasets. `server.py` needs
`pip install markdown`, and runs the validator on startup.

Running either tool, except with `--check`, updates each resource's `count` in
`datapackage.json`, and rewrites the README of each dataset that passes. In a
README, text below `<!-- notes -->` is kept and everything above it is replaced.

## What a dataset needs

- `name`, `title` and `description`.
- `keywords`: exactly `task:<any>`, `project:<any>` and `stage:<master|curated|annotated|ground-truth>`,
   and no others. A folder ending in `-atd` must be `annotated`, and one ending in `-gt`
   must be `ground-truth`.
- `created`, in the form `2026-10-26T00:00:00Z`.
- `contributors`, each with a `title`.
- `resources`, with a `name`, `title` and `path` for every root file and folder, except
   those listed in `rules.json`. A folder covers its contents; prefer a trailing slash
   on its path and omit `format`.
- `buckets.csv`, as described below.
- `sources` are optional. Each one listed needs a `title`.

## Writing descriptions

Describe what the numbers can't capture, such as why the dataset exists, how it
was made and what to watch out for.

Don't describe spread, item counts or people. These belong in `buckets.csv`,
resource `count` and `contributors`.

## Buckets

`buckets.csv` holds the metadata that matters most for the dataset's task, such
as spread (pages per year), error types (count per type) or agreement scores
(percent per metric). Choose whatever fits the task.

Start with a named label column, followed by the numeric value columns. Do not add
an index column. Use `DataFrame.to_csv(..., index=False)` when exporting with pandas.
See `buckets.ipynb` for an example.

For example:

```csv
year,count
1956,201
1957,78
```

Re-export existing indexed summaries with `index=False`; the validator does not
silently remove columns.

## Resource counts

`count` records items, not bytes. It is a lab extension: an optional positive integer.
Counts are computed automatically; don't edit them by hand. `0` means empty; an omitted
count means unknown or unsupported.

| Resource | `count` counts |
| --- | --- |
| `.csv` | Rows, not counting the header |
| `.json` | Top-level array items or object members |
| Folder | Files at any depth, excluding hidden files and hidden folders |
| Other types or multi-path resources | No computed count |

Folder paths are also a lab extension. Omit their `format`: directories are containers,
not file formats. Standard Data Package [`bytes`](https://datapackage.org/standard/data-resource/#bytes)
remains available for storage size. Do not sum resource counts into a dataset total;
resources may describe the same items.

### Existing datasets

A normal run recomputes `count`, removes legacy resource `size` fields and removes
directory `format` fields. It preserves `bytes` and other metadata. Review the
resulting diff before committing. `--check` never writes or migrates files.

The JSON report now uses `counts_written` instead of `sizes_written`.

## Checks

```sh
uv run --locked python -B -m unittest discover -p 'test_*.py'
node --test static/*.test.mjs
```
