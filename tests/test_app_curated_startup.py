from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from core.catalog_bootstrap import resolve_landing_root, sync_curated_catalog_for_runtime


class CuratedCatalogStartupTests(unittest.TestCase):
    def test_resolver_prefers_packaged_landing_then_workspace_sibling(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            workspace = Path(temporary_directory)
            app_root = workspace / "animator"
            sibling = workspace / "surprizopus"
            packaged = app_root / "surpriz"
            app_root.mkdir()
            sibling_manifest = sibling / "data" / "catalogs.json"
            sibling_manifest.parent.mkdir(parents=True)
            sibling_manifest.write_text("{}", encoding="utf-8")

            self.assertEqual(resolve_landing_root(app_root), sibling.resolve())
            packaged_manifest = packaged / "data" / "catalogs.json"
            packaged_manifest.parent.mkdir(parents=True)
            packaged_manifest.write_text("{}", encoding="utf-8")
            self.assertEqual(resolve_landing_root(app_root), packaged.resolve())

    def test_resolver_honors_explicit_override(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            explicit = Path(temporary_directory) / "landing"
            self.assertEqual(
                resolve_landing_root(Path(temporary_directory) / "app", str(explicit)),
                explicit.resolve(),
            )

    def test_development_logs_missing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            logger = Mock()
            result = sync_curated_catalog_for_runtime(
                landing_root=Path(temporary_directory),
                runtime_environment="development",
                sync_catalog=Mock(),
                logger=logger,
            )

            self.assertEqual(result["reason"], "manifest_missing")
            logger.warning.assert_called_once()

    def test_production_rejects_missing_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaisesRegex(RuntimeError, "manifest is missing"):
                sync_curated_catalog_for_runtime(
                    landing_root=Path(temporary_directory),
                    runtime_environment="production",
                    sync_catalog=Mock(),
                    logger=Mock(),
                )

    def test_production_rejects_sync_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            landing_root = Path(temporary_directory)
            manifest = landing_root / "data" / "catalogs.json"
            manifest.parent.mkdir()
            manifest.write_text("{}", encoding="utf-8")
            sync_catalog = Mock(side_effect=ValueError("invalid manifest"))

            with self.assertRaisesRegex(RuntimeError, "synchronization failed"):
                sync_curated_catalog_for_runtime(
                    landing_root=landing_root,
                    runtime_environment="production",
                    sync_catalog=sync_catalog,
                    logger=Mock(),
                )

    def test_valid_manifest_invokes_sync(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            landing_root = Path(temporary_directory)
            manifest = landing_root / "data" / "catalogs.json"
            manifest.parent.mkdir()
            manifest.write_text("{}", encoding="utf-8")
            sync_catalog = Mock(return_value={"changed": True, "count": 42})
            logger = Mock()

            result = sync_curated_catalog_for_runtime(
                landing_root=landing_root,
                runtime_environment="production",
                sync_catalog=sync_catalog,
                logger=logger,
            )

            self.assertEqual(result["count"], 42)
            sync_catalog.assert_called_once_with(manifest)
            logger.info.assert_called_once()


if __name__ == "__main__":
    unittest.main()
