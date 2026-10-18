#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Build the tested Apple TV 16.2.5 Romania compatibility patch offline.

Requires the user's original LG application folder, containing AppleTV,
appinfo.json and res/. Writes only two modified JavaScript resources and a
manifest into a new, separate directory. Does not connect to or install on a TV.
No Apple application, binary, credentials or private keys are bundled here.
"""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path


ORIGINAL_JS = {
    "app.js": "43f0d73af0b75b92ff2f135dddede5cdbe38915233639c1b6e652930af284109",
    "main.js": "9e27c975bcdffa3caeff19d167d6c06f927d96d7f600482d02c1271d926ac713",
    "4239.js": "14defc8cee346e6cb5a80ab8e881425c71fce20b2e5b5130145fff4b35985592",
}
FINAL_JS = {
    "app.js": "f4a751398e0e7a211556586d811798a94d25eaef27e4c85954bb88c92ff2dba3",
    "main.js": "6c3958261062f649785c551da25f89620173896721a63d0d08f7fa0fc77774f3",
    "4239.js": ORIGINAL_JS["4239.js"],
}
PROTECTED_FILES = {
    "AppleTV": "d9f2da54d1c1e9ae7f9d14a8fecac13f963c99ee0eda40f0a5a52ac8f362f64a",
    "appinfo.json": "c0c9f72d4f70dbbc4f1bb23a4eb237a7a7a2a9331170d076afa7f5cd18d35ef8",
}


class PatchError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def compact_json(value):
    return json.dumps(value, separators=(",", ":"))


# Only the missing Romanian UTS routing metadata is supplied. Other countries
# keep the existing native behavior. These are public catalogue endpoints.
FALLBACK = compact_json({
    "routes": {
        "search-landing-path": "/uts/search/landing",
        "init-config-path": "/uts/init/config",
        "configurations-v3-path": "/uts/v3/configurations",
    },
    "nowplaying-enabled": True,
    "uts-api-base-url": "https://uts-api.itunes.apple.com/",
    "uts-api-preview-url": "https://uts-api.itunes.apple.com/",
    "max-local-settings-age-seconds": 15552000,
    "init-config-get-url-length-limit": "2048",
})
WEB_BODY = compact_json({"featureFlags": {"clientFeatures": [
    {"name": name, "domain": "tvapp", "enabled": True}
    for name in ["catch_up_to_live", "opal", "plato", "server_side_one_tap_multiview"]
]}})

# Narrow search/replacement fragments; these are not the complete application.
APP_REPLACEMENTS = [
    (
        "initial_country_ro",
        'g=new tA.DeviceConfiguration(a.locale,void 0)',
        'g=new tA.DeviceConfiguration(a.locale,"ro")',
    ),
    (
        "missing_snapshot_uvsearch_only_ro",
        '_getBagValue(e){try{if(!this.staticBag)throw Error("AMSKit - Snapshot Bag not initialized");return this.staticBag.getValue(e)}catch(e){if(e instanceof r.AMSError&&e.containsCode(r.ErrorCode.valueMissing))return;throw e}}',
        '_getBagValue(e){try{if(!this.staticBag)throw Error("AMSKit - Snapshot Bag not initialized");'
        'let t;try{t=this.staticBag.getValue(e)}catch(n){if(!(n instanceof r.AMSError&&n.containsCode(r.ErrorCode.valueMissing)))throw n}'
        'if("uvSearch"===e&&null==t){let e;try{e=this.staticBag.getValue("countryCode")}catch(t){}'
        'if("ro"===String(e||"").toLowerCase())return '
        + FALLBACK + '}'
        'return t}catch(e){if(e instanceof r.AMSError&&e.containsCode(r.ErrorCode.valueMissing))return;throw e}}',
    ),
    (
        "missing_incoming_uvsearch_only_ro",
        'getUTSPathParameters(e){let{routes:{"configurations-v3-path":t},"uts-api-base-url":i}=e?null==e?void 0:e.uvSearch:this.bag.getBagValue("uvSearch");return i.endsWith("/")&&(i=i.slice(0,-1)),{uts_host:i=ru.x.prefixDomainForITMS(i),init_path:t,base_url:i+"/uts/"}}',
        'getUTSPathParameters(e){let __lgUv=e?e.uvSearch:this.bag.getBagValue("uvSearch");'
        'if(null==__lgUv&&e&&"ro"===String(e.countryCode||"").toLowerCase()){__lgUv='
        + FALLBACK + '}'
        'let{routes:{"configurations-v3-path":t},"uts-api-base-url":i}=__lgUv;'
        'return i.endsWith("/")&&(i=i.slice(0,-1)),{uts_host:i=ru.x.prefixDomainForITMS(i),init_path:t,base_url:i+"/uts/"}}',
    ),
    (
        "ro_storefront_configuration_query",
        'esAppName:eL.w.Config.packageName};oy.thirdPartyIAP',
        'esAppName:eL.w.Config.packageName};'
        'const __lgRo="143487"===String(e).split("-")[0].split(",")[0];'
        'if(__lgRo){u.caller="web";u.pfm="web";u.v="100";delete u.mfr;}'
        'oy.thirdPartyIAP',
    ),
    (
        "ro_configuration_request_body",
        'let f=m.length?{featureFlags:{clientFeatures:m,utsVersion:"V20K"}}:{},y=await this.rawRequest("POST",g,{"Accept-Language":d,"Content-Type":"application/json"},f);try{',
        'let f=__lgRo?' + WEB_BODY + ':m.length?{featureFlags:{clientFeatures:m,utsVersion:"V20K"}}:{},'
        'y=await this.rawRequest("POST",g,{"Accept-Language":d,"Content-Type":"application/json"},f);try{',
    ),
]
MAIN_REPLACEMENT = (
    "freeze_ota_for_this_patch",
    'if (true) {\n            const jsupdater = new JSUpdater({',
    'if (false) {\n            const jsupdater = new JSUpdater({',
)


def guarded_read(root, relative, expected):
    path = root / relative
    if path.is_symlink() or not path.is_file():
        raise PatchError("Expected a regular original file: " + str(path))
    if root not in path.resolve().parents:
        raise PatchError("Source file resolves outside the original folder: " + relative)
    raw = path.read_bytes()
    actual = sha256(raw)
    if actual != expected:
        raise PatchError("Unknown or modified " + relative + "; SHA-256: " + actual)
    return raw


def replace_once(text, name, before, after):
    count = text.count(before)
    if count != 1:
        raise PatchError("Patch " + name + " expected one match, found " + str(count))
    return text.replace(before, after, 1)


def build(source, output):
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise PatchError("--source must name the original application folder")
    if output.exists() or output.is_symlink():
        raise PatchError("Output already exists; choose a new directory: " + str(output))
    output = output.resolve()
    if output == source or source in output.parents:
        raise PatchError("Output must be separate from the original application folder")

    originals = {
        name: guarded_read(source, "res/" + name, expected)
        for name, expected in ORIGINAL_JS.items()
    }
    protected = {
        name: guarded_read(source, name, expected)
        for name, expected in PROTECTED_FILES.items()
    }
    appinfo = json.loads(protected["appinfo.json"].decode("utf-8"))
    if (appinfo.get("id"), appinfo.get("version"), appinfo.get("main")) != (
        "com.apple.appletv", "16.2.5", "AppleTV"
    ):
        raise PatchError("Unexpected application identity or version")

    app_text = originals["app.js"].decode("utf-8")
    for name, before, after in APP_REPLACEMENTS:
        app_text = replace_once(app_text, name, before, after)
    main_text = replace_once(originals["main.js"].decode("utf-8"), *MAIN_REPLACEMENT)
    results = {
        "app.js": app_text.encode("utf-8"),
        "main.js": main_text.encode("utf-8"),
        "4239.js": originals["4239.js"],
    }
    for name, raw in results.items():
        if sha256(raw) != FINAL_JS[name]:
            raise PatchError("Unexpected final checksum for " + name)

    changed = [name for name in ORIGINAL_JS if originals[name] != results[name]]
    if changed != ["app.js", "main.js"]:
        raise PatchError("Unexpected set of modified files")
    manifest = {
        "formatVersion": 1,
        "kind": "lg-appletv-romania-native-js-compatibility",
        "application": {"id": "com.apple.appletv", "version": "16.2.5", "main": "AppleTV"},
        "files": [
            {
                "path": "res/" + name,
                "originalSHA256": ORIGINAL_JS[name],
                "finalSHA256": FINAL_JS[name],
                "originalBytes": len(originals[name]),
                "finalBytes": len(results[name]),
            }
            for name in changed
        ],
        "protectedFiles": [
            {"path": name, "sha256": expected, "modified": False}
            for name, expected in PROTECTED_FILES.items()
        ] + [{"path": "res/4239.js", "sha256": ORIGINAL_JS["4239.js"], "modified": False}],
        "authenticationAndDRMUnchanged": True,
        "diagnosticHooksInserted": False,
        "otaUpdatesFrozenByPatch": True,
        "requiresNewReviewAfterApplicationUpdate": True,
    }

    # Every input and final digest is validated before creating output.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700, exist_ok=False)
    try:
        (output / "res").mkdir(mode=0o700)
        for name in changed:
            with (output / "res" / name).open("xb") as handle:
                handle.write(results[name])
        with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(manifest, handle, indent=2)
            handle.write("\n")
    except BaseException:
        # This directory was exclusively created by this invocation.
        shutil.rmtree(output)
        raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="Original application directory containing AppleTV, appinfo.json and res/")
    parser.add_argument("--output", type=Path, required=True,
                        help="New output directory outside the original application folder")
    args = parser.parse_args()
    try:
        manifest = build(args.source, args.output)
    except (PatchError, OSError, UnicodeError, ValueError) as error:
        print("Refused: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"status": "prepared", "output": str(args.output.resolve()),
                      "modifiedFiles": [entry["path"] for entry in manifest["files"]],
                      "protectedFilesVerified": len(manifest["protectedFiles"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
