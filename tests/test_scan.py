from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import scan

RG_TF = '''terraform {
  required_version = ">= 1.8, < 2.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 4.0, < 5.0"
    }
  }
}'''


def tf_with(constraint):
    return RG_TF.replace(">= 4.0, < 5.0", constraint)


class FakeGitHub:
    def __init__(self, repos, versions=None):
        self.repos = repos
        self.versions = versions or ["5.0.0", "4.1.0"]
        self.calls = 0

    def search_repos(self, owner):
        return sorted(self.repos)

    def tags(self, owner, repo):
        return [(n, v["sha"]) for n, v in self.repos[repo].items()]

    def root_tf_texts(self, owner, repo, ref):
        self.calls += 1
        for n, v in self.repos[repo].items():
            if n == ref or v["sha"] == ref:
                return v["tf"]
        return []

    def azurerm_versions(self):
        return self.versions


def make_fake():
    return FakeGitHub({
        "a": {
            "v1.0.0": {"sha": "s1", "tf": [tf_with(">= 3.0, < 4.0")]},
            "v1.1.0": {"sha": "s2", "tf": ["# nothing", tf_with(">= 4.0, < 5.0")]},
            "release-x": {"sha": "s3", "tf": [RG_TF]},
        },
        "b": {},
    })


class ExtractTests(unittest.TestCase):
    def test_test_repo_layout(self):
        self.assertEqual(scan.extract_azurerm_constraint(RG_TF), ">= 4.0, < 5.0")

    def test_commented_version_ignored(self):
        tf = RG_TF.replace('version = ">= 4.0, < 5.0"', '# version = "~> 3.0"\n      version = "~>4.52"')
        self.assertEqual(scan.extract_azurerm_constraint(tf), "~>4.52")

    def test_no_required_providers(self):
        self.assertIsNone(scan.extract_azurerm_constraint('resource "azurerm_resource_group" "x" {}'))

    def test_other_provider_only(self):
        tf = 'terraform {\n required_providers {\n azuread = {\n source = "hashicorp/azuread"\n version = "~> 3.0"\n }\n }\n}'
        self.assertIsNone(scan.extract_azurerm_constraint(tf))

    def test_azurerm_next_to_azuread(self):
        tf = RG_TF.replace("azurerm = {", 'azuread = {\n source = "hashicorp/azuread"\n version = "~> 3.0"\n }\n azurerm = {')
        self.assertEqual(scan.extract_azurerm_constraint(tf), ">= 4.0, < 5.0")

    def test_source_omitted(self):
        tf = RG_TF.replace('source  = "hashicorp/azurerm"\n', "")
        self.assertEqual(scan.extract_azurerm_constraint(tf), ">= 4.0, < 5.0")

    def test_registry_source(self):
        for src in ("registry.terraform.io/hashicorp/azurerm", "Registry.Terraform.io/HashiCorp/AzureRM"):
            tf = RG_TF.replace("hashicorp/azurerm", src)
            self.assertEqual(scan.extract_azurerm_constraint(tf), ">= 4.0, < 5.0")

    def test_foreign_source(self):
        tf = RG_TF.replace("hashicorp/azurerm", "other/azurerm")
        self.assertIsNone(scan.extract_azurerm_constraint(tf))

    def test_block_and_slash_comments(self):
        tf = RG_TF.replace(
            'version = ">= 4.0, < 5.0"',
            '/* version = "~> 3.0" */\n      // version = "~> 2.0"\n      version = "~> 4.1" # trailing',
        )
        self.assertEqual(scan.extract_azurerm_constraint(tf), "~> 4.1")

    def test_azurerm_without_version(self):
        tf = RG_TF.replace('version = ">= 4.0, < 5.0"', "")
        self.assertIsNone(scan.extract_azurerm_constraint(tf))


class TagTests(unittest.TestCase):
    def test_release_tags(self):
        self.assertTrue(scan.is_release_tag("v1.2.0"))
        self.assertTrue(scan.is_release_tag("v0.0.1"))
        for name in ["1.2.0", "v1.2", "v5.0.0-rc1", "release-1", "latest"]:
            self.assertFalse(scan.is_release_tag(name))


class ScanTests(unittest.TestCase):
    NOW = "2026-11-05T03:00:00Z"

    def test_first_scan(self):
        res = scan.scan("floriandevries", None, make_fake(), self.NOW)
        self.assertEqual(res["owner"], "floriandevries")
        self.assertEqual(res["azurerm_versions"], ["5.0.0", "4.1.0"])
        self.assertEqual(res["modules"]["a"]["tags"], {
            "v1.0.0": {"sha": "s1", "constraint": ">= 3.0, < 4.0"},
            "v1.1.0": {"sha": "s2", "constraint": ">= 4.0, < 5.0"},
        })
        self.assertEqual(res["modules"]["b"]["tags"], {})
        self.assertEqual(res["modules"]["a"]["url"], "https://github.com/floriandevries/a")
        self.assertEqual(res["updated_at"], self.NOW)

    def test_missing_constraint_is_null(self):
        fake = FakeGitHub({"a": {"v1.0.0": {"sha": "s1", "tf": ['resource "x" "y" {}']}}})
        res = scan.scan("o", None, fake, self.NOW)
        self.assertIsNone(res["modules"]["a"]["tags"]["v1.0.0"]["constraint"])

    def test_unchanged_tag_is_not_reread(self):
        first = scan.scan("floriandevries", None, make_fake(), self.NOW)
        fake = make_fake()
        scan.scan("floriandevries", first, fake, "later")
        self.assertEqual(fake.calls, 0)

    def test_moved_tag_is_reread(self):
        first = scan.scan("floriandevries", None, make_fake(), self.NOW)
        fake = make_fake()
        fake.repos["a"]["v1.1.0"] = {"sha": "s9", "tf": [tf_with("~> 5.0")]}
        res = scan.scan("floriandevries", first, fake, "later")
        self.assertEqual(res["modules"]["a"]["tags"]["v1.1.0"], {"sha": "s9", "constraint": "~> 5.0"})
        self.assertEqual(fake.calls, 1)
        self.assertEqual(res["updated_at"], "later")

    def test_deleted_tag_and_lost_topic_are_dropped(self):
        first = scan.scan("floriandevries", None, make_fake(), self.NOW)
        fake = make_fake()
        del fake.repos["a"]["v1.0.0"]
        del fake.repos["b"]
        res = scan.scan("floriandevries", first, fake, "later")
        self.assertNotIn("v1.0.0", res["modules"]["a"]["tags"])
        self.assertNotIn("b", res["modules"])

    def test_updated_at_kept_when_nothing_changed(self):
        first = scan.scan("floriandevries", None, make_fake(), self.NOW)
        res = scan.scan("floriandevries", first, make_fake(), "later")
        self.assertEqual(res["updated_at"], self.NOW)

    def test_updated_at_changes_with_versions(self):
        first = scan.scan("floriandevries", None, make_fake(), self.NOW)
        fake = make_fake()
        fake.versions = ["5.1.0", "5.0.0", "4.1.0"]
        res = scan.scan("floriandevries", first, fake, "later")
        self.assertEqual(res["updated_at"], "later")


class SearchTests(unittest.TestCase):
    def test_incomplete_results_raise(self):
        pages = [{"incomplete_results": True, "items": [{"name": "a"}]}]
        gh = scan.GitHub("t")
        with mock.patch.object(gh, "_json_pages", return_value=iter(pages)):
            with self.assertRaises(urllib.error.URLError):
                gh.search_repos("o")

    def test_complete_results_return_sorted_names(self):
        pages = [{"incomplete_results": False, "items": [{"name": "b"}, {"name": "a"}]}]
        gh = scan.GitHub("t")
        with mock.patch.object(gh, "_json_pages", return_value=iter(pages)):
            self.assertEqual(gh.search_repos("o"), ["a", "b"])


class CliTests(unittest.TestCase):
    def test_api_error_leaves_file_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "catalog.json")
            with open(path, "wb") as f:
                f.write(b'{"known": true}\n')
            with mock.patch.dict(os.environ, {"GH_TOKEN": "t"}), \
                    mock.patch.object(scan.GitHub, "search_repos", side_effect=urllib.error.URLError("boom")):
                self.assertEqual(scan.main(["--owner", "x", "--out", path]), 1)
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b'{"known": true}\n')

    def test_missing_token_returns_1(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "catalog.json")
            env = {k: v for k, v in os.environ.items() if k != "GH_TOKEN"}
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(scan.main(["--owner", "x", "--out", path]), 1)
            self.assertFalse(os.path.exists(path))

    def test_writes_only_when_changed(self):
        fake = make_fake()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "catalog.json")
            with mock.patch.dict(os.environ, {"GH_TOKEN": "t"}), \
                    mock.patch.object(scan, "GitHub", return_value=fake):
                self.assertEqual(scan.main(["--owner", "o", "--out", path]), 0)
                with open(path) as f:
                    first = f.read()
                self.assertTrue(first.endswith("}\n"))
                self.assertRegex(json.loads(first)["updated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
                mtime = os.stat(path).st_mtime_ns
                self.assertEqual(scan.main(["--owner", "o", "--out", path]), 0)
                with open(path) as f:
                    self.assertEqual(f.read(), first)
                self.assertEqual(os.stat(path).st_mtime_ns, mtime)


if __name__ == "__main__":
    unittest.main()
