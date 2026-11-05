#!/usr/bin/env python3
"""Offline tests: all subprocesses/network in the guided workflow are fakes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("lg_installer", Path(__file__).resolve().parents[1] / "install.py")
wizard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wizard)


def encoded(value):
    return (json.dumps(value) + "\n").encode()


def success_receipt(operation):
    return {"kind": "lg-appletv-ro-overlay-result-v1", "status": "success", "mode": operation,
            "committed": True, "appId": "com.apple.appletv", "modifiedFiles": wizard.RESOURCE_PATHS[:],
            "outputSHA256": (wizard.FINAL if operation == "apply" else wizard.ORIGINAL).copy(),
            "originalNativeIdentityUnchanged": True, "originalImageUnchanged": True,
            "original4239Unchanged": True, "appDataRead": False, "databaseWritesPerformed": False,
            "installedPersistentRoot": False,
            "actions": {"ownStageRemoved": True, "exportStageRemoved": operation == "apply"}}


class FakeRunner:
    def __init__(self, metadata=None, edit_receipt=None, missing_receipt=False, loader_returncode=0,
                 developer_uid=6303):
        self.metadata = metadata or wizard.REFERENCE.copy()
        self.commands, self.operations, self.remote = [], [], {}
        self.edit_receipt = edit_receipt or (lambda operation, receipt: receipt)
        self.missing_receipt = missing_receipt
        self.loader_returncode = loader_returncode
        self.developer_uid = developer_uid
        self.archive = b"private original archive fixture"

    def run(self, arguments, **options):
        args = [str(item) for item in arguments]
        self.commands.append((args, options))
        command = Path(args[0]).name
        output = ""
        code = 0
        if command == "ares-device":
            output = "\n".join(key + " : " + value for key, value in self.metadata.items()) + "\n"
        elif command == "ares-novacom" and args[-1] == "id -u":
            output = "[Info] Set target device : test\n" + str(self.developer_uid) + "\n"
        elif command == "node" and Path(args[1]).name == "pull_file.cjs":
            remote, target = args[3], Path(args[4])
            if remote not in self.remote:
                raise wizard.Stop("missing fake receipt")
            target.write_bytes(self.remote[remote])
            target.chmod(0o600)
        elif len(args) > 1 and Path(args[1]).name == "prepare_bundle.py":
            operation = args[2]
            folder = Path(args[args.index("--output") + 1])
            folder.mkdir(mode=0o700)
            stage = "/media/internal/downloads/lg-appletv-ro-" + operation + "-" + "a" * 16
            receipt = stage + "/result.json" if operation == "export" else (
                "/media/developer/temp/lg-appletv-ro-" + stage.rsplit("/", 1)[1] + "-result.json")
            names = {"slopbro.py", "wwwroot/index.html", "wwwroot/package.json", "wwwroot/main.js",
                     "wwwroot/transaction.json", "COPYING"}
            if operation != "export":
                names |= {"wwwroot/payload-app.js", "wwwroot/payload-main.js"}
            hashes = {}
            for name in names:
                target = folder / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"offline fixture, never executed")
                hashes[name] = wizard.file_sha(target)
            wizard.save_json(folder / "bundle.json", {
                "formatVersion": 1, "operation": operation, "remoteStage": stage,
                "receiptRemote": receipt, "upstreamCommit": wizard.PIN, "persistentRoot": False,
                "containsLocallyGeneratedAppleResources": operation != "export",
                "developerModeUid": int(args[args.index("--developer-uid") + 1]), "files": hashes})
            data = wizard.read_json(folder / "bundle.json")
            data["patchProfile"] = args[args.index("--profile") + 1] if "--profile" in args else "c3"
            wizard.save_json(folder / "bundle.json", data)
        elif len(args) > 1 and Path(args[1]).name == "slopbro.py":
            bundle = wizard.read_json(Path(args[1]).parent / "bundle.json")
            operation = bundle["operation"]
            self.operations.append(operation)
            if operation == "export":
                receipt = {"status": "success", "kind": "lg-appletv-ro-export-v1", "appId": "com.apple.appletv",
                           "stage": bundle["remoteStage"], "archivePath": bundle["remoteStage"] + "/apple-tv-original.tar",
                           "archiveSHA256": hashlib.sha256(self.archive).hexdigest(), "archiveBytes": len(self.archive),
                           "originalFilesModified": False, "originalDataRead": False, "databaseRecordsRead": False,
                           "persistentRootInstalled": False, "installedPersistentRoot": False, "installedHomebrew": False,
                           "preservedNativeFlags": {"id": "com.apple.appletv", "version": "16.2.4" if self.metadata == wizard.C2_METADATA else "16.2.5", "main": "AppleTV",
                                                    "type": "native", "trustLevel": "trusted", "privilegedJail": True}}
                self.remote[receipt["archivePath"]] = self.archive
            else:
                receipt = success_receipt(operation)
            receipt = self.edit_receipt(operation, receipt)
            if not self.missing_receipt:
                self.remote[bundle["receiptRemote"]] = encoded(receipt)
            code = self.loader_returncode
        elif len(args) > 1 and Path(args[1]).name == "verify_export.py":
            folder = Path(args[args.index("--output") + 1])
            (folder / wizard.APP / "res").mkdir(parents=True)
            for relative in wizard.RESOURCE_PATHS:
                (folder / wizard.APP / relative).write_bytes(b"private fixture")
        elif len(args) > 1 and Path(args[1]).name == "check_compatibility.py":
            output = json.dumps({"status": "known-input-fingerprints-match",
                                 "packageAssessment": {"requiredOriginalInputsMatch": True, "nativeIdentityMatches": True},
                                 "installedImageAssessment": {"matches": True}})
        elif len(args) > 1 and Path(args[1]).name == "build_patch.py":
            folder = Path(args[args.index("--output") + 1])
            (folder / "res").mkdir(parents=True)
            for relative in wizard.RESOURCE_PATHS:
                (folder / relative).write_bytes(b"private fixture")
        elif command in ("ares-config", "ares-setup-device", "ares-novacom") or (
                command == "node" and args[1] == "--check"):
            pass
        else:
            raise AssertionError("Unexpected fake command: " + repr(args))
        return subprocess.CompletedProcess(args, code, output, "")


class OfflineInstaller(wizard.Installer):
    def fetch_upstream(self):
        folder = self.folder / "slopbro-source"
        folder.mkdir(mode=0o700)
        return folder


class FakePrerequisites:
    def __init__(self, root):
        self.prefix = root / "uninstalled-system-prefix"
        self.installed = False
        self.commands = []

    def which(self, name):
        return "/fake/" + name if name in ("node", "npm") or self.installed else None

    def use_prefix(self, prefix):
        self.prefix = prefix

    def run(self, arguments, **options):
        args = [str(item) for item in arguments]
        self.commands.append((args, options))
        if args == ["node", "--version"]:
            output = "v20.19.0\n"
        elif args == ["npm", "root", "-g"]:
            output = str(self.prefix / "lib" / "node_modules") + "\n"
        elif args[:2] == ["npm", "install"]:
            self.assert_prefix = args[args.index("--prefix") + 1]
            target = self.prefix / "lib" / "node_modules" / "@webos-tools" / "cli" / "package.json"
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps({"version": "3.2.6"}))
            self.installed = True
            output = ""
        elif args[-1] == "--version" and args[0].startswith("ares-"):
            output = "Version: 3.2.6\n"
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, output, "")


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lg-installer-offline-")
        self.root = Path(self.temporary.name)
        (self.root / wizard.DEVELOPER_MODE_PROFILES).write_text(json.dumps({
            "formatVersion": 1,
            "profiles": [{**wizard.REFERENCE, "developerModeUids": [6303, 6322]},
                         {**wizard.C2_METADATA, "developerModeUids": [6322]}],
        }))

    def tearDown(self):
        self.temporary.cleanup()

    def engine(self, **options):
        runner = FakeRunner(**options)
        return OfflineInstaller(root=self.root, runner=runner, ask=lambda text: "da", say=lambda text: None, sleep=lambda value: None), runner

    def test_check_never_starts_root(self):
        engine, runner = self.engine()
        engine.run("check", "192.168.1.20")
        self.assertEqual(engine.state["status"], "checked")
        self.assertEqual(runner.operations, [])

    def test_allowed_newer_developer_mode_uid_is_recorded(self):
        engine, runner = self.engine(developer_uid=6322)
        engine.run("check", "192.168.1.20")
        self.assertEqual(engine.state["developerModeUid"], 6322)
        self.assertEqual(runner.operations, [])

    def test_unknown_developer_mode_uid_stops_before_root(self):
        engine, runner = self.engine(developer_uid=7000)
        with self.assertRaises(wizard.Stop):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, [])

    def test_profiles_selected_using_detected_tv(self):
        c2 = {"modelName": "OLED77C21LA", "firmwareVersion": "33.31.68", "sdkVersion": "10.3.1"}
        (self.root / wizard.DEVELOPER_MODE_PROFILES).write_text(json.dumps({
            "formatVersion": 1, "profiles": [
                {**wizard.REFERENCE, "developerModeUids": [6303]},
                {**c2, "developerModeUids": [6322]},
            ]}))
        engine, runner = self.engine(metadata=c2, developer_uid=6322)
        engine.run("check", "192.168.1.20")
        self.assertEqual(engine.allowed_developer_uids, frozenset([6322]))
        self.assertTrue(engine.state["referenceMatches"])
        engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, ["export", "apply"])
        other, _ = self.engine(metadata=c2, developer_uid=6303)
        with self.assertRaises(wizard.Stop):
            other.run("check", "192.168.1.20")

    def test_unknown_model_refused_before_export(self):
        metadata = wizard.REFERENCE.copy()
        metadata["modelName"] = "OLED55C31LA"
        engine, runner = self.engine(metadata=metadata)
        with self.assertRaises(wizard.Stop):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, [])
        self.assertEqual(engine.state["status"], "stopped")

    def test_configuration_cannot_enable_an_unknown_patch_profile(self):
        unknown = dict(wizard.REFERENCE, modelName="OTHER")
        (self.root / wizard.DEVELOPER_MODE_PROFILES).write_text(json.dumps({
            "formatVersion": 1, "profiles": [{**unknown, "developerModeUids": [6303]}]}))
        engine, runner = self.engine(metadata=unknown)
        with self.assertRaises(wizard.Stop):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, [])

    def test_ambiguous_or_invalid_uid_profiles_refused(self):
        for values in ([0], [True], ["6322"], [], [6322, 6322]):
            with self.subTest(values=values):
                (self.root / wizard.DEVELOPER_MODE_PROFILES).write_text(json.dumps({
                    "formatVersion": 1, "profiles": [{**wizard.REFERENCE,"developerModeUids":values}]}))
                with self.assertRaises(wizard.Stop):
                    wizard.developer_mode_uids(self.root,wizard.REFERENCE)
        entry = {**wizard.REFERENCE,"developerModeUids":[6303]}
        (self.root / wizard.DEVELOPER_MODE_PROFILES).write_text(json.dumps({
            "formatVersion":1,"profiles":[entry,entry]}))
        with self.assertRaises(wizard.Stop):
            wizard.developer_mode_uids(self.root,wizard.REFERENCE)

    def test_apply_and_restore_order_and_private_state(self):
        engine, runner = self.engine()
        engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, ["export", "apply"])
        self.assertEqual(engine.state["status"], "applied")
        self.assertFalse(engine.state["playbackConfirmed"])
        self.assertEqual((engine.folder / "session.json").stat().st_mode & 0o777, 0o600)
        restore, second = self.engine()
        restore.run("restore", "192.168.1.20", engine.folder)
        self.assertEqual(second.operations, ["restore"])
        self.assertEqual(restore.state["status"], "restored")

    def test_c2_apply_restore_profile_and_loader_version(self):
        engine, runner = self.engine(metadata=wizard.C2_METADATA, developer_uid=6322)
        engine.run("apply", "192.168.1.20")
        self.assertEqual(engine.state["patchProfile"], "c2")
        for args, options in runner.commands:
            if len(args) > 1 and Path(args[1]).name == "slopbro.py":
                self.assertEqual(args[args.index("--webos-version") + 1], "10")
            if len(args) > 2 and Path(args[1]).name in ("build_patch.py", "check_compatibility.py"):
                self.assertEqual(args[args.index("--profile") + 1], "c2")
        restore, second = self.engine(metadata=wizard.C2_METADATA, developer_uid=6322)
        restore.run("restore", "192.168.1.20", engine.folder)
        self.assertEqual(second.operations, ["restore"])
        self.assertEqual(restore.state["status"], "restored")

    def test_c3_loader_stays_on_11(self):
        engine, runner = self.engine()
        engine.run("apply", "192.168.1.20")
        for args, options in runner.commands:
            if len(args) > 1 and Path(args[1]).name == "slopbro.py":
                self.assertEqual(args[args.index("--webos-version") + 1], "11")

    def test_cross_profile_restore_refused_before_root(self):
        engine, _ = self.engine()
        engine.run("apply", "192.168.1.20")
        restore, runner = self.engine(metadata=wizard.C2_METADATA, developer_uid=6322)
        with self.assertRaises(wizard.Stop):
            restore.run("restore", "192.168.1.20", engine.folder)
        self.assertEqual(runner.operations, [])

    def test_changed_device_before_export_stops_before_root(self):
        engine, runner = self.engine()
        def decline_and_change(question):
            runner.metadata = wizard.C2_METADATA
            return "da"
        engine.ask = decline_and_change
        with self.assertRaises(wizard.Stop):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, [])

    def test_changed_uid_before_export_stops_before_root(self):
        engine, runner = self.engine()
        def change_uid(question):
            runner.developer_uid = 6322
            return "da"
        engine.ask = change_uid
        with self.assertRaises(wizard.Stop):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, [])

    def test_legacy_c3_backup_can_restore(self):
        engine, _ = self.engine()
        engine.run("apply", "192.168.1.20")
        saved = wizard.read_json(engine.folder / "session.json")
        del saved["developerModeUid"]
        del saved["patchProfile"]
        wizard.save_json(engine.folder / "session.json", saved)
        manifest = engine.folder / "export-bundle/bundle.json"
        data = wizard.read_json(manifest)
        del data["developerModeUid"]
        del data["patchProfile"]
        wizard.save_json(manifest, data)
        restore, runner = self.engine()
        restore.run("restore", "192.168.1.20", engine.folder)
        self.assertEqual(runner.operations, ["restore"])

    def test_receipt_beats_loader_returncode(self):
        engine, runner = self.engine(loader_returncode=1)
        engine.run("apply", "192.168.1.20")
        self.assertEqual(engine.state["status"], "applied")
        self.assertEqual(runner.operations, ["export", "apply"])

    def test_missing_receipt_never_reexecutes_loader(self):
        engine, runner = self.engine(missing_receipt=True)
        with self.assertRaises(wizard.NeedsAttention):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, ["export"])
        self.assertEqual(engine.state["status"], "needs-attention")

    def test_export_scope_refusal_stops_before_apply(self):
        def edit(operation, receipt):
            if operation == "export":
                receipt["originalDataRead"] = True
            return receipt
        engine, runner = self.engine(edit_receipt=edit)
        with self.assertRaises(wizard.Stop):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, ["export"])

    def test_partial_commit_no_retry_or_rollback_claim(self):
        def edit(operation, receipt):
            if operation == "apply":
                receipt.update(status="failed", committed=True)
            return receipt
        engine, runner = self.engine(edit_receipt=edit)
        with self.assertRaises(wizard.NeedsAttention):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(runner.operations, ["export", "apply"])
        self.assertEqual(engine.state["status"], "needs-attention")

    def test_failed_rollback_requires_attention(self):
        def edit(operation, receipt):
            if operation == "apply":
                receipt.update(status="failed", committed=False, rollbackErrors=["rollback failed"])
            return receipt
        engine, runner = self.engine(edit_receipt=edit)
        with self.assertRaises(wizard.NeedsAttention):
            engine.run("apply", "192.168.1.20")
        self.assertEqual(engine.state["status"], "needs-attention")
        self.assertEqual(runner.operations, ["export", "apply"])

    def test_invalid_postwrite_receipts_always_require_attention(self):
        changes = [{"kind": "unknown"}, {"mode": "restore"}, {"outputSHA256": {}},
                   {"originalImageUnchanged": False}, {"installedPersistentRoot": True},
                   {"modifiedFiles": []}, {"appId": "different"}, {"committed": False}]
        for changed in changes:
            with self.subTest(changed=changed):
                def edit(operation, receipt):
                    if operation == "apply":
                        receipt.update(changed)
                    return receipt
                engine, runner = self.engine(edit_receipt=edit)
                with self.assertRaises(wizard.NeedsAttention):
                    engine.run("apply", "192.168.1.20")
                self.assertEqual(engine.state["status"], "needs-attention")
                self.assertEqual(runner.operations, ["export", "apply"])

    def test_unconfirmed_cleanup_is_attention_not_success(self):
        def edit(operation, receipt):
            if operation == "apply":
                receipt["actions"]["ownStageRemoved"] = False
            return receipt
        engine, runner = self.engine(edit_receipt=edit)
        with self.assertRaises(wizard.NeedsAttention):
            engine.run("apply", "192.168.1.20")
        self.assertNotEqual(engine.state["status"], "applied")
        self.assertEqual(runner.operations.count("apply"), 1)

    def test_restore_other_ip_refused_before_root(self):
        engine, _ = self.engine()
        engine.run("apply", "192.168.1.20")
        restore, runner = self.engine()
        with self.assertRaises(wizard.Stop):
            restore.run("restore", "192.168.1.21", engine.folder)
        self.assertEqual(runner.operations, [])

    def test_modified_backup_refused_before_restore(self):
        engine, _ = self.engine()
        engine.run("apply", "192.168.1.20")
        (engine.folder / "apple-tv-original.tar").write_bytes(b"changed")
        restore, runner = self.engine()
        with self.assertRaises(wizard.Stop):
            restore.run("restore", "192.168.1.20", engine.folder)
        self.assertEqual(runner.operations, [])

    def test_metadata_parse_fails_closed(self):
        good = "\n".join(key + " : " + value for key, value in wizard.REFERENCE.items())
        self.assertEqual(wizard.parse_system_info(good), wizard.REFERENCE)
        for invalid in ("OLED77C31LA 43.21.71 11.2.0", good + "\nmodelName : OTHER", good + "\nerror", ""):
            with self.subTest(invalid=invalid), self.assertRaises(wizard.Stop):
                wizard.parse_system_info(invalid)

    def test_ip_validation(self):
        for invalid in ("127.0.0.1", "8.8.8.8", "192.168.1.1;whoami", "::1", "", "0.0.0.0"):
            with self.subTest(invalid=invalid), self.assertRaises(wizard.Stop):
                wizard.validate_ip(invalid)

    def test_runner_uses_argv_without_shell(self):
        with patch.object(wizard.subprocess, "run", return_value=subprocess.CompletedProcess(["dummy"], 0, "", "")) as call:
            wizard.Runner().run(["dummy", "literal;argument"])
        self.assertFalse(call.call_args.kwargs["shell"])
        self.assertEqual(call.call_args.args[0], ["dummy", "literal;argument"])

    def test_cli_installation_uses_private_prefix_without_sudo(self):
        runner = FakePrerequisites(self.root)
        wizard.prerequisites(runner, ask=lambda question: "da", say=lambda message: None, root=self.root)
        self.assertEqual(runner.prefix, self.root / "backup" / "tool-runtime")
        self.assertEqual(runner.assert_prefix, str(runner.prefix))
        self.assertFalse(any("sudo" in args for args, options in runner.commands))

    def test_declined_cli_install_does_not_install(self):
        runner = FakePrerequisites(self.root)
        with self.assertRaises(wizard.Stop):
            wizard.prerequisites(runner, ask=lambda question: "nu", say=lambda message: None, root=self.root)
        self.assertFalse(runner.installed)

    def test_prefix_propagates_to_node_transfer(self):
        runner = wizard.Runner()
        runner.use_prefix(self.root)
        with patch.object(wizard.subprocess, "run", return_value=subprocess.CompletedProcess(["node"], 0, "", "")) as call:
            runner.run(["node", "pull_file.cjs"])
        environment = call.call_args.kwargs["env"]
        self.assertEqual(environment["npm_config_prefix"], str(self.root))
        self.assertTrue(environment["PATH"].startswith(str(self.root / "bin") + ":"))



if __name__ == "__main__":
    unittest.main(verbosity=2)
