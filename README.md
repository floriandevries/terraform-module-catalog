# Terraform module catalog

Static GitHub Pages catalog of Terraform modules. A scheduled workflow scans an owner's repos, records the azurerm constraint of every release tag in `catalog.json`, and the page matches those constraints against an azurerm version you pick.

Test modules: `terraform-azurerm-fjdev-res-resource-group`, `terraform-azurerm-fjdev-res-logic-app-standard`, `terraform-azurerm-fjdev-res-mssql-managed-instance`.

## How "supported" is decided

- Repos need both topics `terraform` and `azurerm`.
- Only tags matching `^v\d+\.\d+\.\d+$` count. Pre-releases and other tags are ignored.
- The scanner reads the azurerm `version` constraint from the root `.tf` files at each tag.
- A release is shown as compatible only if its parsed constraint allows the selected azurerm version. A missing or unparseable constraint is never compatible.

## Run tests locally

```
python3 -m unittest discover -s tests
node --test tests/*.test.js
```

## Run a scan locally

```
GH_TOKEN=$(gh auth token) python3 scripts/scan.py --owner floriandevries --out catalog.json
```

The file is rewritten only when the content changed. Exit code 1 means an API error or a missing token, and the file is left untouched. If fetching one tag fails, the whole run aborts; re-run it later.

## Token

The workflow uses the built-in `github.token`, which can read public repos only. Private module repos need a GitHub App token.

## Pages setup

Settings, Pages: deploy from branch `main`, folder `/`.

## Moving to another owner

Change `--owner` in `.github/workflows/scan.yml` and the token. For Cegeka that means org `Cegeka-Hybrid-Cloud`, repo name `pc-cc-tf-modules-catalog`, private Pages, and a GitHub App instead of `github.token`.
