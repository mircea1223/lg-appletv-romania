#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Compare a private, exported Apple TV application with tested patch inputs.

Offline and read-only: no TV connection, installation, extraction, or patching.
JSON goes to stdout. Exit 0 means the required input fingerprints match (and
data.img matches if supplied), NOT that a TV is compatible or playback works.
Exit 1 means unknown/missing/modified inputs; exit 2 means invalid source input.
"""

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path


REFERENCE = {
    "model": "OLED77C31LA",
    "firmware": "43.21.71",
    "sdk": "11.2.0",
    "applicationVersion": "16.2.5",
    "authenticationAndSubscriptionPlayback": "confirmed-by-owner-on-one-TV",
}
INPUTS = {
    "res/app.js": (
        "43f0d73af0b75b92ff2f135dddede5cdbe38915233639c1b6e652930af284109",
        16 * 1024 * 1024,
    ),
    "res/main.js": (
        "9e27c975bcdffa3caeff19d167d6c06f927d96d7f600482d02c1271d926ac713",
        16 * 1024 * 1024,
    ),
    "res/4239.js": (
        "14defc8cee346e6cb5a80ab8e881425c71fce20b2e5b5130145fff4b35985592",
        16 * 1024 * 1024,
    ),
    "AppleTV": (
        "d9f2da54d1c1e9ae7f9d14a8fecac13f963c99ee0eda40f0a5a52ac8f362f64a",
        64 * 1024 * 1024,
    ),
    "appinfo.json": (
        "c0c9f72d4f70dbbc4f1bb23a4eb237a7a7a2a9331170d076afa7f5cd18d35ef8",
        65536,
    ),
}
IMAGE_SHA256 = "e80efaa39e92afe81b6218e6bb11d2c1e40d46b25f371d7cb18cf19807116221"
IDENTITY = {
    "id": "com.apple.appletv",
    "version": "16.2.5",
    "main": "AppleTV",
    "type": "native",
    "trustLevel": "trusted",
    "privilegedJail": True,
}


def stable_fingerprint(path, maximum):
    """Reject links/special files and changes while reading a bounded file."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > maximum:
        raise ValueError("Expected a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(path), flags)
    try:
        opened = os.fstat(descriptor)
        attributes = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        original_state = tuple(getattr(before, item) for item in attributes)
        if not stat.S_ISREG(opened.st_mode) or tuple(
            getattr(opened, item) for item in attributes
        ) != original_state:
            raise ValueError("File identity changed before reading")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > maximum:
                raise ValueError("File grew beyond its size limit")
            digest.update(block)
        if total != opened.st_size or tuple(
            getattr(os.fstat(descriptor), item) for item in attributes
        ) != original_state:
            raise ValueError("File changed while reading")
        return digest.hexdigest(), total
    finally:
        os.close(descriptor)


def check_file(path, label, expected, maximum):
    row = {"path": label, "expectedSHA256": expected, "matches": False}
    try:
        actual, size = stable_fingerprint(path, maximum)
        row.update({"actualSHA256": actual, "bytes": size, "matches": actual == expected})
        row["status"] = "match" if row["matches"] else "unknown-or-modified"
    except (OSError, ValueError) as error:
        # No absolute paths, file contents, device identifiers, or account data.
        row.update({"status": "unreadable-or-invalid", "errorType": type(error).__name__})
    return row


def supplied_text(value):
    text = value.strip()
    if not text or len(text) > 128 or any(ord(character) < 32 for character in text):
        raise argparse.ArgumentTypeError("Use a nonempty model or version, up to 128 characters")
    return text


def assess(args):
    supplied = {name: getattr(args, name) for name in ("model", "firmware", "sdk")}
    supplied_keys = [name for name, value in supplied.items() if value is not None]
    config_match = None
    if any(supplied[name] != REFERENCE[name] for name in supplied_keys):
        config_match = False
    elif len(supplied_keys) == 3:
        config_match = True
    report = {
        "formatVersion": 1,
        "tool": "lg-appletv-ro-offline-compatibility-check",
        "status": "invalid-source",
        "readOnly": True,
        "networkContactPerformed": False,
        "referenceConfiguration": REFERENCE,
        "suppliedDeviceMetadata": supplied,
        "suppliedMetadataMatchesReference": config_match,
        "suppliedMetadataIndependentlyVerified": False,
        "packageAssessment": {
            "requiredOriginalInputsMatch": False,
            "completeApplicationEqualityProven": False,
            "checks": [],
        },
        "installedImageAssessment": {"status": "not-provided", "matches": None},
        "currentDeviceAssessment": {
            "rootRuntimeAndFilesystemVerified": False,
            "authenticationAndPlaybackTestPerformed": False,
            "playbackConfirmed": False,
            "installationApprovedByThisTool": False,
        },
    }
    try:
        if args.source.is_symlink() or not args.source.is_dir():
            raise ValueError("Source must be a real original application directory")
        source = args.source.resolve(strict=True)
    except (OSError, ValueError):
        report["error"] = "Source is missing, unreadable, or not a real directory"
        return report, 2

    checks = []
    for relative, (expected, maximum) in INPUTS.items():
        path = source / relative
        # A symlinked res/ could otherwise point outside the selected export.
        parents_safe = all(
            not parent.is_symlink() and parent.is_dir()
            for parent in path.parents if parent != source and source in parent.parents
        )
        if parents_safe:
            row = check_file(path, relative, expected, maximum)
        else:
            row = {"path": relative, "expectedSHA256": expected, "matches": False,
                   "status": "invalid-parent-directory"}
        checks.append(row)
    inputs_match = all(row["matches"] for row in checks)
    report["packageAssessment"].update({"checks": checks, "requiredOriginalInputsMatch": inputs_match})
    # The exact manifest digest already pins identity, including the trusted jail.
    # Only parse a manifest whose digest matches, avoiding output of unknown data.
    identity_matches = False
    if checks[-1]["matches"]:
        try:
            manifest = json.loads((source / "appinfo.json").read_text(encoding="utf-8"))
            identity_matches = all(manifest.get(key) == value for key, value in IDENTITY.items())
        except (OSError, ValueError, UnicodeError, AttributeError):
            pass
    report["packageAssessment"]["nativeIdentityMatches"] = identity_matches
    inputs_match = inputs_match and identity_matches
    report["packageAssessment"]["requiredOriginalInputsMatch"] = inputs_match

    image_matches = True
    if args.image is not None:
        image_row = check_file(args.image, "data.img", IMAGE_SHA256, 512 * 1024 * 1024)
        report["installedImageAssessment"] = image_row
        image_matches = image_row["matches"]
    accepted = inputs_match and image_matches
    report["status"] = "known-input-fingerprints-match" if accepted else "unknown-or-modified-inputs"
    report["nextStep"] = (
        "Offline inputs match; inspect target runtime and filesystem before any installation. "
        "Playback on this device remains unverified."
        if accepted else
        "Stop. Do not remove or change checksum guards; inspect the different original package first."
    )
    return report, 0 if accepted else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Exported original directory containing AppleTV, appinfo.json and res/")
    parser.add_argument("--image", type=Path,
                        help="Optional private export of the original registered data.img")
    parser.add_argument("--model", type=supplied_text, help="Exact model, e.g. OLED77C31LA")
    parser.add_argument("--firmware", type=supplied_text, help="Reported firmware version, e.g. 43.21.71")
    parser.add_argument("--sdk", type=supplied_text, help="SDK version, e.g. 11.2.0; not marketing webOS 26")
    report, code = assess(parser.parse_args())
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
