from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch
from tools.validate import (
    find_yaml_files,
    find_yaml_serialization_violations,
    load_json_document,
    main,
    validate,
    validate_family_inventory,
    validate_manifest_document,
    validate_project_config,
    validate_project_profile,
    _read_object,
)


ROOT = Path(__file__).resolve().parents[1]


class ValidateTests(unittest.TestCase):
    def test_repository_contract_passes(self) -> None:
        self.assertEqual(validate(ROOT), [])

    def test_readme_matches_repository_role_and_current_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("docs/DATA_FORMAT_AND_ARCHITECTURE_POLICY.md", readme)
        self.assertIn("docs/YAML_MIGRATION.md", readme)
        self.assertIn("config/project.example.toml", readme)

        if ROOT.name.endswith("_Dev"):
            self.assertIn("HADA Base Template (Development)", readme)
            self.assertIn("tools/validate.py --dev", readme)
        else:
            self.assertNotIn("(Development)", readme)
            self.assertNotIn("SPEC.md", readme)
            self.assertNotIn("--dev", readme)
            if ROOT.name.endswith("_Sample"):
                self.assertIn("HADA Base Template — Sample", readme)
                self.assertIn("fictional", readme.lower())
            else:
                self.assertTrue(readme.startswith("# HADA Base Template\n"))

    def test_dev_mode_requires_internal_specifications(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "WHY.md", "README.md", "CHANGELOG.md", "TEMPLATE_BASE.md",
                "AI/README.md", "config/template-manifest.json", "tools/validate.py",
                "tools/upgrade.py",
            ):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            manifest_path = root / "config/template-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["artifact_role"] = "base_dev"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root, dev=True)
            self.assertTrue(any("SPEC.md" in error for error in errors))
            self.assertTrue(any("ReSPEC.md" in error for error in errors))

    def test_version_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (
                "AGENTS.md", "WHY.md", "README.md",
                "CHANGELOG.md", "TEMPLATE_BASE.md", "AI/README.md",
                "config/template-manifest.json", "tools/validate.py", "tools/upgrade.py",
            ):
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read_bytes())
            manifest_path = root / "config/template-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["template"]["version"] = "9.9.9"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            errors = validate(root)
            self.assertTrue(any("TEMPLATE_BASE.md version" in error for error in errors))

    def test_yaml_files_are_rejected_without_creating_a_fixture(self) -> None:
        prohibited = ROOT / "data" / "legacy.yml"
        with patch("tools.validate.find_yaml_files", return_value=[prohibited]):
            errors = validate(ROOT)

        self.assertIn("YAML files are prohibited: data/legacy.yml", errors)

    def test_yaml_only_gate_checks_multiple_non_base_project_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            template = Path(directory) / "specialized-template"
            project = Path(directory) / "derived-project"
            template.mkdir()
            (project / "data").mkdir(parents=True)
            prohibited = project / "data" / "legacy.YML"
            prohibited.write_text("external: value\n", encoding="utf-8")
            output = StringIO()

            with redirect_stdout(output):
                code = main([
                    "--yaml-only",
                    "--root", str(template),
                    "--root", str(project),
                ])

            self.assertEqual(code, 1)
            self.assertIn("PASS: no YAML files", output.getvalue())
            self.assertIn("data/legacy.YML", output.getvalue())
            self.assertFalse((template / "config" / "template-manifest.json").exists())

            prohibited.unlink()
            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "--yaml-only",
                    "--root", str(template),
                    "--root", str(project),
                ])

            self.assertEqual(code, 0)
            self.assertEqual(output.getvalue().count("PASS: no YAML files"), 2)

            output = StringIO()
            with redirect_stdout(output):
                code = main([
                    "--yaml-only",
                    "--root", str(template),
                    "--root", str(Path(directory) / "missing-project"),
                ])

            self.assertEqual(code, 1)
            self.assertIn("cannot resolve YAML migration root", output.getvalue())

    def test_yaml_scanner_does_not_claim_success_through_symlink_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def walk_with_symlink(*_args, **_kwargs):
                yield str(root), ["linked"], []

            with patch("tools.validate.os.walk", side_effect=walk_with_symlink):
                with patch.object(Path, "is_symlink", return_value=True):
                    with self.assertRaisesRegex(OSError, "symlink directory: linked"):
                        find_yaml_files(root)

    def test_manifest_schema_rejects_unknown_properties_and_duplicate_json_keys(self) -> None:
        manifest = json.loads((ROOT / "config/template-manifest.json").read_text(encoding="utf-8"))
        manifest["unrecognized"] = True
        self.assertTrue(any("Additional properties" in error for error in validate_manifest_document(manifest)))
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.json"
            duplicate.write_text('{"manifest_version":"1.1.0","manifest_version":"1.1.0"}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate object key"):
                load_json_document(duplicate)
            nonstandard = Path(directory) / "nonstandard.json"
            nonstandard.write_text('{"value":NaN}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "non-standard JSON constant"):
                load_json_document(nonstandard)

    def test_contract_reader_refuses_symbolic_link_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "manifest.json"
            target.write_text("{}", encoding="utf-8")
            errors: list[str] = []
            with patch.object(
                Path,
                "is_symlink",
                autospec=True,
                side_effect=lambda candidate: candidate == target,
            ):
                value = _read_object(target, "manifest", errors)
            self.assertIsNone(value)
            self.assertEqual(errors, ["manifest must not be a symbolic link"])

    def test_project_configuration_schema_rejects_unknown_properties_and_wrong_types(self) -> None:
        self.assertEqual(validate_project_config({"features": {"conversation_logging": False}}), [])
        self.assertTrue(validate_project_config({
            "features": {"conversation_logging": "false"},
            "unrecognized": True,
        }))

    def test_sample_project_profile_matches_its_declared_schema(self) -> None:
        profile_path = ROOT / "examples/fictional-project/project.json"
        if not profile_path.exists():
            self.skipTest("fictional project profile is distributed in Sample only")
        profile = load_json_document(profile_path)
        self.assertEqual(validate_project_profile(profile), [])

    def test_family_gate_requires_complete_inventory_and_exact_roots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temporary_root = Path(directory)
            template_root = temporary_root / "specialized"
            project_root = temporary_root / "project"
            template_root.mkdir()
            project_root.mkdir()
            inventory_path = temporary_root / "family.json"
            members = [
                {
                    "id": "content-template",
                    "kind": "specialized_template",
                    "locator": "HADA_Content_Studio_Template",
                    "adoption_state": "compliant",
                    "base_compatibility": {
                        "template_id": "hada-base-template",
                        "minimum_version": "0.2.0",
                        "tested_version": "0.2.0",
                    },
                },
                {
                    "id": "content-project",
                    "kind": "data_project",
                    "locator": "HADA_Content_Project",
                    "adoption_state": "compliant",
                    "base_compatibility": {
                        "template_id": "hada-base-template",
                        "minimum_version": "0.2.0",
                        "tested_version": "0.2.0",
                    },
                },
            ]
            inventory = {
                "schema_version": "1.0.0",
                "family_id": "content-family",
                "inventory_revision": 1,
                "inventory_complete": True,
                "members": members,
            }
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            roots = [
                f"content-template={template_root}",
                f"content-project={project_root}",
            ]
            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, roots)
            self.assertEqual(code, 0, output.getvalue())
            self.assertIn('"status": "PASS"', output.getvalue())

            output = StringIO()
            same_root = [roots[0], f"content-project={template_root}"]
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, same_root)
            self.assertEqual(code, 1)
            self.assertIn("resolve to the same directory", output.getvalue())

            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, roots[:1])
            self.assertEqual(code, 1)
            self.assertIn("family roots are missing registered members", output.getvalue())

            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, roots + [roots[0]])
            self.assertEqual(code, 1)
            self.assertIn("duplicate family root ID", output.getvalue())

            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(
                    inventory_path,
                    roots + [f"unregistered={temporary_root / 'unregistered'}"],
                )
            self.assertEqual(code, 1)
            self.assertIn("unregistered members", output.getvalue())

            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(
                    inventory_path,
                    [roots[0], f"content-project={temporary_root / 'missing'}"],
                )
            self.assertEqual(code, 1)
            self.assertIn("cannot be fully scanned", output.getvalue())

            yaml_file = project_root / "legacy.yaml"
            yaml_file.write_text("legacy: true\n", encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, roots)
            self.assertEqual(code, 1)
            self.assertIn("still contains YAML: legacy.yaml", output.getvalue())
            yaml_file.unlink()

            parser_file = template_root / "parse_yaml.py"
            parser_file.write_text("from ruamel import yaml\n", encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, roots)
            self.assertEqual(code, 1)
            self.assertIn("YAML parser/serializer import is prohibited", output.getvalue())
            parser_file.unlink()

            inventory["members"][1]["adoption_state"] = "migrating"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, roots)
            self.assertEqual(code, 1)
            self.assertIn("is not marked compliant", output.getvalue())

            inventory["inventory_complete"] = False
            inventory["members"][1]["adoption_state"] = "compliant"
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, roots)
            self.assertEqual(code, 1)
            self.assertIn("not owner-attested complete", output.getvalue())

            inventory["inventory_complete"] = True
            inventory["members"][0]["id"] = []
            inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                code = validate_family_inventory(inventory_path, roots)
            self.assertEqual(code, 1)
            self.assertIn("member IDs must be present and unique", output.getvalue())

    def test_yaml_serialization_imports_and_requirements_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools").mkdir()
            (root / "tools" / "parse.py").write_text("import yaml\n", encoding="utf-8")
            (root / "requirements.txt").write_text(
                "ruamel.yaml>=0.18\ngit+https://example.invalid/team/yaml-parser.git#egg=PyYAML\n",
                encoding="utf-8",
            )
            errors = find_yaml_serialization_violations(root)
            self.assertEqual(len(errors), 3)
            self.assertTrue(any("import is prohibited" in error for error in errors))
            self.assertTrue(any("dependency is prohibited" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
