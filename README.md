# haste-pages

Charts [haste](https://github.com/ykjit/haste) results from merged PRs on GitHub Pages.

Each PR attaches haste's `data.toml` and `extra.toml` as `haste.zip` archive, to its
description. When the PR merges, the build action extracts them to `<PR number>/` on the `haste-results` branch and charts every PR there.

## Run

```
example
├── 2              # Merged PR #2
│   ├── data.toml
│   ├── extra.toml
│   └── pr.json    # PR info
├── 3              # Merged PR #3
│   ├── data.toml
│   ├── extra.toml
│   └── pr.json
├── data.toml      # An open PR's results
└── extra.toml
```

```shell
uv run src/main.py ykjit/ykmruby example   # writes site/index.html
```

Chart a real interpreter, with haste-pages and the interpreter checked out side by side:

```shell
cd ../ykmruby
git clone -b haste-results https://github.com/ykjit/ykmruby results
uv run ../haste-pages/src/main.py ykjit/ykmruby results
```

## Test

```shell
uv run python -m unittest discover tests
```

## Usage

```yaml
name: Haste pages
on:
  push:
    branches: [master]
  workflow_dispatch:            # Rebuild by hand, e.g. after committing an older PR's
                                # <PR number>/ to haste-results.
  pull_request_target:          # Remind job only. Not pull_request: fork PRs cannot comment.
    types: [opened]
jobs:
  pages:                        # Stores the merged PR's results and deploys the chart.
    if: github.event_name != 'pull_request_target'
    runs-on: ubuntu-latest
    # contents: write pushes to haste-results; pull-requests: read finds the merged PR's
    # attachments; the others deploy Pages.
    permissions: { contents: write, pull-requests: read, pages: write, id-token: write }
    environment: { name: github-pages, url: "${{ steps.deploy.outputs.page_url }}" }
    concurrency: { group: pages }
    steps:
      - uses: ykjit/haste-pages/action/build@v1
      - id: deploy
        uses: actions/deploy-pages@v4
  remind:                       # Optional: comments on new PRs that do not attach
                                # haste.zip.
    if: github.event_name == 'pull_request_target'
    runs-on: ubuntu-latest
    permissions: { pull-requests: write }
    steps:
      - uses: ykjit/haste-pages/action/remind@v1
```

Releases: tag `v1.x.y` and move `v1` to it.
