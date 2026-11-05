#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Guided wrapper for the guarded tools. Importing this file performs no I/O.

macOS/Linux; Python 3.9+, Node 20+. Portable workflow tested offline only.
The television is contacted only after a menu choice and an IP are entered.
"""

import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import uuid
from tools.c2_profile import METADATA as C2_METADATA


ROOT = Path(__file__).resolve().parent
REFERENCE = {"modelName": "OLED77C31LA", "firmwareVersion": "43.21.71", "sdkVersion": "11.2.0"}
PROFILE_METADATA = {"c3": REFERENCE, "c2": C2_METADATA}
PROFILE_VERSION = {"c3": "16.2.5", "c2": "16.2.4"}
PROFILE_WEBOS = {"c3": "11", "c2": "10"}
DEVELOPER_MODE_PROFILES = "developer_mode_profiles.json"
APP = "media/cryptofs/apps/usr/palm/applications/com.apple.appletv"
IMAGE = "media/cryptofs/apps/usr/palm/data/images/com.apple.appletv/data.img"
CLI_VERSION = "3.2.6"
PIN = "21023d56ca424607bb03d2939609cc658c655fc7"
STAGE = re.compile(r"/media/internal/downloads/lg-appletv-ro-(export|apply|restore)-[a-f0-9]{16}\Z")
RESOURCE_PATHS = ["res/app.js", "res/main.js"]
FINAL = {"res/app.js": "f4a751398e0e7a211556586d811798a94d25eaef27e4c85954bb88c92ff2dba3",
         "res/main.js": "6c3958261062f649785c551da25f89620173896721a63d0d08f7fa0fc77774f3"}
ORIGINAL = {"res/app.js": "43f0d73af0b75b92ff2f135dddede5cdbe38915233639c1b6e652930af284109",
            "res/main.js": "9e27c975bcdffa3caeff19d167d6c06f927d96d7f600482d02c1271d926ac713"}


class Stop(Exception):
    """A refusal; never silently retried as another root operation."""


class NeedsAttention(Stop):
    """A write may have happened, so no automatic retry is permitted."""


def require(condition, message):
    if not condition:
        raise Stop(message)


def read_json(path):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size <= 2 * 1024 * 1024,
            "Fișier de rezultat lipsă, prea mare sau nesigur: " + path.name)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as error:
        raise Stop("Rezultatul nu este JSON valid: " + path.name) from error
    require(isinstance(value, dict), "Format de rezultat necunoscut: " + path.name)
    return value


def save_json(path, value):
    """Private atomic, durable state writes; keep every workspace for diagnosis."""
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def file_sha(path):
    require(not path.is_symlink() and path.is_file(), "Fișier local nesigur: " + path.name)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def private_directory(path, create=False):
    if create and not path.exists() and not path.is_symlink():
        path.mkdir(mode=0o700)
    require(not path.is_symlink() and path.is_dir(), "Director privat lipsă sau nesigur: " + str(path))
    info = path.stat()
    require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
            "Directorul trebuie să îți aparțină și să aibă permisiuni 700: " + str(path))
    return path


def parse_system_info(text):
    """CLI 3.2.6 has no JSON flag; parse its fixed key:value TV output strictly.

    Source: webos-tools/cli 3.2.6 lib/device.js, tvSystemInfo.__makeReturnObj.
    Values come from the device query, never from user-entered model numbers.
    """
    require(isinstance(text, str) and len(text) <= 32768, "Informații TV invalide.")
    fields = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or re.fullmatch(r"\[Info\] Set target device : [A-Za-z0-9_.-]+", line):
            continue
        match = re.fullmatch(r"(modelName|firmwareVersion|sdkVersion|boardType|otaId)\s*:\s*([^\r\n]+)", line)
        require(match is not None, "Nu pot interpreta sigur răspunsul ares-device. Nu pornesc root.")
        key, value = match.groups()
        require(key not in fields, "ares-device a întors câmpuri duplicate. Nu pornesc root.")
        fields[key] = value.strip()
    require(all(key in fields for key in REFERENCE), "Lipsește modelul, firmware-ul sau SDK-ul. Nu pornesc root.")
    return {key: fields[key] for key in REFERENCE}


def validate_ip(value):
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as error:
        raise Stop("Introdu numai IP-ul local al TV-ului, de forma 192.168.x.x.") from error
    require(address.version == 4 and address.is_private and not any(
        (address.is_loopback, address.is_unspecified, address.is_multicast, address.is_link_local)),
        "Este necesar un IP IPv4 din rețeaua locală.")
    return str(address)


def developer_mode_uids(root, metadata):
    """Load the explicit Developer Mode UID allowlist for one exact TV profile."""
    data = read_json(root / DEVELOPER_MODE_PROFILES)
    require(data.get("formatVersion") == 1 and isinstance(data.get("profiles"), list),
            "Configurația UID Developer Mode nu este validă.")
    matches = []
    for profile in data["profiles"]:
        if not isinstance(profile, dict) or any(profile.get(key) != metadata.get(key) for key in REFERENCE):
            continue
        values = profile.get("developerModeUids")
        require(isinstance(values, list) and values and all(
            isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535 for value in values
        ) and len(set(values)) == len(values), "Lista UID Developer Mode nu este validă.")
        matches.append(frozenset(values))
    require(len(matches) == 1, "Nu există un profil UID unic pentru modelul, firmware-ul și SDK-ul verificate.")
    return matches[0]


class Runner:
    def __init__(self):
        self.environment = os.environ.copy()
        # CLI capture is parsed as data, including when FORCE_COLOR is set in a shell.
        self.environment["NO_COLOR"] = "1"
        self.environment.pop("FORCE_COLOR", None)

    def use_prefix(self, prefix):
        self.environment["npm_config_prefix"] = str(prefix)
        self.environment.pop("NPM_CONFIG_PREFIX", None)
        self.environment["PATH"] = str(prefix / "bin") + os.pathsep + self.environment.get("PATH", "")

    def which(self, name):
        return shutil.which(name, path=self.environment.get("PATH"))

    def run(self, arguments, cwd=None, interactive=False, timeout=90, check=True):
        try:
            result = subprocess.run([str(item) for item in arguments], cwd=cwd,
                                    capture_output=not interactive, text=True, timeout=timeout,
                                    shell=False, env=self.environment)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Stop("Comanda nu s-a încheiat: " + Path(str(arguments[0])).name) from error
        if check and result.returncode:
            # Captured output may contain SSH device details; don't echo it into reports.
            raise Stop("Comanda a eșuat: " + Path(str(arguments[0])).name +
                       ". Verifică Developer Mode, Key Server și conexiunea.")
        return result


def prerequisites(runner, ask=input, say=print, root=ROOT):
    require(sys.platform in ("darwin", "linux"), "Deocamdată instalatorul este pentru macOS/Linux.")
    require(sys.version_info >= (3, 9), "Instalează Python 3.9 sau mai nou: https://www.python.org/downloads/")
    require(os.getuid() != 0, "Pornește programul ca utilizator normal, fără sudo.")
    require(runner.which("node") and runner.which("npm"),
            "Instalează Node.js 20+ (include npm): https://nodejs.org/ — apoi redeschide Terminalul.")
    version = runner.run(["node", "--version"]).stdout.strip()
    require(re.fullmatch(r"v\d+\.\d+\.\d+", version) is not None and int(version.split(".")[0][1:]) >= 20,
            "Este necesar Node.js 20 sau mai nou: https://nodejs.org/")
    local_prefix = root / "backup" / "tool-runtime"
    if local_prefix.exists() or local_prefix.is_symlink():
        private_directory(root / "backup")
        private_directory(local_prefix)
        runner.use_prefix(local_prefix)
    global_root = runner.run(["npm", "root", "-g"]).stdout.strip()
    package = Path(global_root) / "@webos-tools" / "cli" / "package.json"
    installed = read_json(package).get("version") if package.is_file() else None
    if installed != CLI_VERSION or not all(runner.which(name) for name in (
            "ares-config", "ares-setup-device", "ares-device", "ares-novacom")):
        say("Este necesar webOS CLI 3.2.6, pachetul oficial LG publicat pe npm.")
        say("Îl pot instala în directorul privat backup/tool-runtime, fără sudo.")
        require(ask("Îl instalez acum? [da/nu]: ").strip().lower() in ("da", "d", "yes", "y"),
                "Oprit. Poți instala separat CLI 3.2.6 și apoi relua programul.")
        private_directory(root / "backup", create=True)
        private_directory(local_prefix, create=True)
        runner.use_prefix(local_prefix)
        runner.run(["npm", "install", "-g", "--prefix", local_prefix, "@webos-tools/cli@3.2.6"],
                   interactive=True, timeout=300)
        package = Path(runner.run(["npm", "root", "-g"]).stdout.strip()) / "@webos-tools" / "cli" / "package.json"
        require(read_json(package).get("version") == CLI_VERSION,
                "Instalarea nu a furnizat versiunea cerută. Nu continua cu alt CLI.")
    for name in ("ares-config", "ares-setup-device", "ares-device", "ares-novacom"):
        require(runner.which(name) is not None, "Comanda " + name + " lipsește din PATH. Redeschide Terminalul.")
        banner = runner.run([name, "--version"]).stdout.strip()
        require(re.search(r"(?<![\d.])3\.2\.6(?![\d.])", banner) is not None,
                "Comanda " + name + " nu provine din CLI 3.2.6. Verifică PATH.")


def validate_bundle(folder, operation, developer_uid, profile="c3"):
    metadata = read_json(folder / "bundle.json")
    stage = metadata.get("remoteStage", "")
    match = STAGE.fullmatch(stage) if isinstance(stage, str) else None
    require(match and match.group(1) == operation, "Locație de lucru TV necunoscută.")
    receipt = (stage + "/result.json" if operation == "export" else
               "/media/developer/temp/lg-appletv-ro-" + stage.rsplit("/", 1)[1] + "-result.json")
    require(metadata.get("formatVersion") == 1 and metadata.get("operation") == operation and
            metadata.get("upstreamCommit") == PIN and metadata.get("persistentRoot") is False and
            metadata.get("developerModeUid", 6303 if profile == "c3" else None) == developer_uid and
            metadata.get("patchProfile", "c3") == profile and
            metadata.get("receiptRemote") == receipt and
            metadata.get("containsLocallyGeneratedAppleResources") is (operation != "export"),
            "Manifestul pachetului temporar nu corespunde operației.")
    expected = {"slopbro.py", "wwwroot/index.html", "wwwroot/package.json", "wwwroot/main.js",
                "wwwroot/transaction.json", "COPYING"}
    if operation != "export":
        expected |= {"wwwroot/payload-app.js", "wwwroot/payload-main.js"}
    hashes = metadata.get("files")
    require(isinstance(hashes, dict) and set(hashes) == expected, "Lista fișierelor temporare nu corespunde.")
    for name, digest in hashes.items():
        require(file_sha(folder / name) == digest, "Pachetul local s-a schimbat: " + name)
    return metadata


def validate_export(result, bundle, profile="c3"):
    stage = bundle["remoteStage"]
    require(result.get("status") == "success" and result.get("kind") == "lg-appletv-ro-export-v1" and
            result.get("appId") == "com.apple.appletv" and result.get("stage") == stage and
            result.get("archivePath") == stage + "/apple-tv-original.tar" and
            re.fullmatch(r"[a-f0-9]{64}", str(result.get("archiveSHA256", ""))) and
            isinstance(result.get("archiveBytes"), int) and result["archiveBytes"] > 0,
            "Backupul nu are o confirmare validă de la TV.")
    for flag in ("originalFilesModified", "originalDataRead", "databaseRecordsRead",
                 "persistentRootInstalled", "installedPersistentRoot", "installedHomebrew"):
        require(result.get(flag) is False, "Backupul nu confirmă păstrarea datelor și lipsa persistenței.")
    identity = result.get("preservedNativeFlags", {})
    require(isinstance(identity, dict) and all(identity.get(key) == value for key, value in {
        "id": "com.apple.appletv", "version": PROFILE_VERSION[profile], "main": "AppleTV", "type": "native",
        "trustLevel": "trusted", "privilegedJail": True}.items()), "Identitatea aplicației native diferă.")


def validate_transaction(result, operation):
    def confirmed(condition, message):
        if not condition:
            raise NeedsAttention(message + " Starea aplicației trebuie verificată; păstrează backupul și nu relua automat.")

    confirmed(result.get("kind") == "lg-appletv-ro-overlay-result-v1" and result.get("mode") == operation,
              "Confirmarea TV nu aparține operației cerute.")
    if result.get("rollbackErrors"):
        raise NeedsAttention("TV-ul raportează erori la revenirea dintr-o aplicare incompletă. "
                             "Starea aplicației trebuie verificată; păstrează backupul și nu relua instalarea.")
    if result.get("committed") is True and result.get("status") != "success":
        raise NeedsAttention("Fișierele au fost scrise, dar curățarea nu s-a încheiat. "
                             "Păstrează backupul și rezultatul; nu relua instalarea automat.")
    confirmed(result.get("status") == "success" and result.get("committed") is True,
              "TV-ul nu a confirmat reușita.")
    confirmed(result.get("appId") == "com.apple.appletv" and result.get("modifiedFiles") == RESOURCE_PATHS and
              result.get("outputSHA256") == (FINAL if operation == "apply" else ORIGINAL),
              "Confirmarea nu conține exact cele două fișiere și amprentele așteptate.")
    for flag in ("originalNativeIdentityUnchanged", "originalImageUnchanged", "original4239Unchanged"):
        confirmed(result.get(flag) is True, "Nu este confirmată păstrarea componentelor originale.")
    for flag in ("appDataRead", "databaseWritesPerformed", "installedPersistentRoot"):
        confirmed(result.get(flag) is False, "Rezultatul nu confirmă limitele operației.")
    actions = result.get("actions", {})
    if not isinstance(actions, dict) or actions.get("ownStageRemoved") is not True or (
            operation == "apply" and actions.get("exportStageRemoved") is not True):
        raise NeedsAttention("Fișierele sunt corecte, dar curățarea nu este confirmată. "
                             "Păstrează rezultatul și cere verificare; nu relua instalarea.")


class Installer:
    def __init__(self, root=ROOT, runner=None, ask=input, say=print, sleep=time.sleep):
        self.root, self.runner, self.ask, self.say, self.sleep = root, runner or Runner(), ask, say, sleep
        self.folder = None
        self.state = {}
        self.allowed_developer_uids = frozenset()
        self.profile = None

    def mark(self, status, **values):
        self.state.update(values)
        self.state["status"] = status
        save_json(self.folder / "session.json", self.state)

    def start(self, operation, ip):
        base = private_directory(self.root / "backup", create=True)
        self.folder = base / ("session-" + time.strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12])
        private_directory(self.folder, create=True)
        self.state = {"formatVersion": 1, "operation": operation, "ip": ip,
                      "device": "appletvro-" + uuid.uuid4().hex[:12], "playbackConfirmed": False}
        self.mark("created")
        self.say("Fișiere private și backup: " + str(self.folder))

    def connect(self):
        device = self.state["device"]
        self.runner.run(["ares-config", "--profile", "tv"])
        info = json.dumps({"host": self.state["ip"], "port": "9922", "username": "prisoner"})
        self.runner.run(["ares-setup-device", "--add", device, "--info", info])
        self.say("În Developer Mode pe TV: Dev Mode Status activ, apoi Key Server activ.")
        self.say("Introdu passphrase-ul direct la solicitarea LG de mai jos. Nu îl publica.")
        self.runner.run(["ares-novacom", "--device", device, "--getkey"], interactive=True, timeout=180)
        developer_uid = self.device_uid()
        metadata = self.device_info()
        self.mark("identified", developerModeUid=developer_uid, metadata=metadata)
        self.allowed_developer_uids = developer_mode_uids(self.root, metadata)
        matches = [name for name, expected in PROFILE_METADATA.items() if metadata == expected]
        require(len(matches) == 1, "Model/firmware/SDK fără un profil de patch verificat. Oprit înainte de root.")
        self.profile = matches[0]
        require(developer_uid in self.allowed_developer_uids,
                "UID Developer Mode " + str(developer_uid) + " nu este acceptat de profilul acestui TV. Oprit.")
        self.mark("connected", developerModeUid=developer_uid, patchProfile=self.profile)
        return metadata

    def device_uid(self):
        uid_output = self.runner.run(["ares-novacom", "--device", self.state["device"], "--run", "id -u"]).stdout
        lines = [line.strip() for line in uid_output.splitlines() if line.strip() and
                 not re.fullmatch(r"\[Info\] Set target device : [A-Za-z0-9_.-]+", line.strip())]
        require(len(lines) == 1 and lines[0].isdigit(), "Nu pot confirma UID-ul Developer Mode. Oprit.")
        return int(lines[0])

    def device_info(self):
        result = self.runner.run(["ares-device", "--system-info", "--device", self.state["device"]])
        return parse_system_info(result.stdout)

    def gate(self, metadata):
        require(self.profile in PROFILE_METADATA and metadata == PROFILE_METADATA[self.profile],
                "Model/firmware/SDK diferă de profilul selectat. Oprit înainte de root.")

    def profile_arguments(self):
        return ["--profile", "c2"] if self.profile == "c2" else []

    def tool(self, name, arguments):
        return self.runner.run([sys.executable, self.root / "tools" / name] + list(arguments), timeout=240)

    def fetch_upstream(self):
        # Import the source-hash allowlist already used by the guarded builder.
        spec = importlib.util.spec_from_file_location("lg_appletv_prepare", self.root / "tools" / "prepare_bundle.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        require(module.PINNED_COMMIT == PIN and set(module.UPSTREAM_SHA) == {
            "slopbro.py", "wwwroot/index.html", "wwwroot/package.json", "COPYING"},
            "Commitul sau lista fișierelor loaderului nu corespunde.")
        destination = self.folder / "slopbro-source"
        private_directory(destination, create=True)
        self.say("Descarc cele patru fișiere ale loaderului fixat și le verific SHA256.")
        for relative, expected in module.UPSTREAM_SHA.items():
            url = "https://raw.githubusercontent.com/throwaway96/slopbro/" + PIN + "/" + relative
            try:
                with urllib.request.urlopen(url, timeout=30) as response:
                    require(response.geturl() == url, "Redirecționare neașteptată la sursa loaderului.")
                    raw = response.read(2 * 1024 * 1024 + 1)
            except OSError as error:
                raise Stop("Nu pot descărca sursa fixată. Nicio aplicare nu a pornit.") from error
            require(len(raw) <= 2 * 1024 * 1024 and hashlib.sha256(raw).hexdigest() == expected,
                    "Sursa descărcată diferă de amprenta fixată. Oprit.")
            target = destination / relative
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with target.open("xb") as handle:
                os.chmod(target, 0o600)
                handle.write(raw)
        return destination

    def prepare(self, operation, upstream, original=None, export=None, archive=None):
        folder = self.folder / (operation + "-bundle")
        arguments = [operation, "--upstream", upstream, "--output", folder,
                     "--developer-uid", str(self.state["developerModeUid"])]
        arguments += self.profile_arguments()
        if original is not None:
            arguments += ["--original", original]
        if export is not None:
            arguments += ["--cleanup-export", export, "--archive", archive]
        self.tool("prepare_bundle.py", arguments)
        return folder, validate_bundle(folder, operation, self.state["developerModeUid"], self.profile)

    def pull(self, remote, target, retries=1):
        for attempt in range(retries):
            try:
                self.runner.run(["node", self.root / "tools" / "pull_file.cjs", self.state["device"], remote, target],
                                timeout=200 if retries == 1 else 20)
                return
            except Stop:
                if target.exists() or target.is_symlink() or attempt + 1 == retries:
                    raise
                self.sleep(2)

    def execute(self, operation, folder, bundle):
        # Re-read both the real device configuration and all bundle hashes immediately before root.
        self.gate(self.device_info())
        require(self.device_uid() == self.state["developerModeUid"],
                "UID-ul Developer Mode s-a schimbat înainte de root. Oprit.")
        require(validate_bundle(folder, operation, self.state["developerModeUid"], self.profile) == bundle,
                "Pachetul s-a schimbat înainte de execuție.")
        self.mark(operation + "-started", activeBundle=str(folder.name))
        self.say("Acces root temporar pentru " + operation + ". Acceptă asocierea afișată pe TV.")
        try:
            self.runner.run([sys.executable, folder / "slopbro.py", "--webos-version", PROFILE_WEBOS[self.profile],
                             "--asset-source", "dir", "--debug", self.state["ip"]],
                            cwd=folder, interactive=True, timeout=420, check=False)
        except Stop:
            self.say("Loaderul s-a oprit. Caut confirmarea TV; nu îl pornesc din nou.")
        receipt = self.folder / (operation + "-result.json")
        try:
            self.pull(bundle["receiptRemote"], receipt, retries=6)
        except Stop as error:
            raise NeedsAttention("Nu am putut prelua confirmarea TV. Rezultatul operației este necunoscut; "
                                 "păstrează directorul privat și nu relua automat.") from error
        try:
            result = read_json(receipt)
        except (Stop, OSError, ValueError) as error:
            if operation != "export":
                raise NeedsAttention("Confirmarea operației nu poate fi citită sigur. "
                                     "Starea aplicației trebuie verificată; nu relua automat.") from error
            raise
        if operation == "export":
            validate_export(result, bundle, self.profile)
        else:
            try:
                validate_transaction(result, operation)
            except Stop as error:
                if result.get("committed") is True:
                    raise NeedsAttention(str(error)) from error
                raise
        self.mark(operation + "-confirmed")
        return result

    def verify_original(self, archive, receipt, output):
        self.tool("verify_export.py", ["--archive", archive, "--result", receipt, "--output", output])
        source = output / APP
        result = self.runner.run([sys.executable, self.root / "check_compatibility.py", "--source", source,
                                  "--image", output / IMAGE] + self.profile_arguments(), timeout=90)
        try:
            report = json.loads(result.stdout)
        except ValueError as error:
            raise Stop("Verificatorul nu a furnizat JSON valid.") from error
        require(isinstance(report, dict) and report.get("status") == "known-input-fingerprints-match" and
                isinstance(report.get("packageAssessment"), dict) and
                isinstance(report.get("installedImageAssessment"), dict) and
                report["packageAssessment"].get("requiredOriginalInputsMatch") is True and
                report["packageAssessment"].get("nativeIdentityMatches") is True and
                report["installedImageAssessment"].get("matches") is True,
                "Aplicația exportată diferă de originalul verificat. Nu aplic corecția.")
        save_json(self.folder / "compatibility.json", report)
        return source

    def apply(self):
        self.gate(self.state["metadata"])
        self.say("Deschide Apple TV din Home și las-o pornită înainte de export.")
        require(self.ask("Apple TV este deschisă? [da/nu]: ").strip().lower() in ("da", "d", "yes", "y"),
                "Deschide Apple TV și reia procedura înainte de export.")
        upstream = self.fetch_upstream()
        export_folder, export_bundle = self.prepare("export", upstream)
        export = self.execute("export", export_folder, export_bundle)
        archive = self.folder / "apple-tv-original.tar"
        self.pull(export["archivePath"], archive)
        require(archive.stat().st_size == export["archiveBytes"], "Mărimea backupului diferă de confirmarea TV.")
        source = self.verify_original(archive, self.folder / "export-result.json", self.folder / "original")
        self.mark("backup-verified", archiveSHA256=file_sha(archive))
        self.tool("build_patch.py", ["--source", source, "--output", self.folder / "patched"] + self.profile_arguments())
        for relative in RESOURCE_PATHS:
            self.runner.run(["node", "--check", self.folder / "patched" / relative])
        folder, bundle = self.prepare("apply", upstream, source, export_folder / "bundle.json", archive)
        self.execute("apply", folder, bundle)
        self.mark("applied", archiveSHA256=file_sha(archive))
        self.say("Corecția și curățarea au fost confirmate. Din Home, deschide Apple TV original.")
        self.say("Autentifică-te pe telefon și pornește un episod cu abonament. Redarea nu este verificată automat.")

    def restore(self, previous):
        self.gate(self.state["metadata"])
        private_directory(previous)
        saved = read_json(previous / "session.json")
        require(saved.get("formatVersion") == 1 and saved.get("operation") == "apply" and
                saved.get("status") == "applied" and saved.get("metadata") == self.state["metadata"] and
                saved.get("patchProfile", "c3") == self.profile and
                saved.get("ip") == self.state["ip"], "Backupul nu aparține unei aplicări confirmate la acest IP.")
        validate_transaction(read_json(previous / "apply-result.json"), "apply")
        old_uid = saved.get("developerModeUid", 6303 if self.profile == "c3" else None)
        require(isinstance(old_uid, int) and not isinstance(old_uid, bool) and old_uid in self.allowed_developer_uids,
                "Backupul nu conține un UID Developer Mode acceptat.")
        old_bundle = validate_bundle(previous / "export-bundle", "export", old_uid, self.profile)
        old_result = read_json(previous / "export-result.json")
        validate_export(old_result, old_bundle, self.profile)
        archive = previous / "apple-tv-original.tar"
        require(file_sha(archive) == saved.get("archiveSHA256") == old_result["archiveSHA256"],
                "Backupul original a fost modificat.")
        source = self.verify_original(archive, previous / "export-result.json", self.folder / "original")
        self.mark("restore-backup-verified", restoredFrom=previous.name)
        upstream = self.fetch_upstream()
        folder, bundle = self.prepare("restore", upstream, source)
        self.execute("restore", folder, bundle)
        self.mark("restored")
        self.say("Cele două fișiere originale au fost restaurate; curățarea este confirmată.")
        self.say("Deschide Apple TV. Eroarea inițială de disponibilitate poate reapărea.")

    def choose_backup(self):
        base = private_directory(self.root / "backup", create=True)
        options = []
        for folder in sorted(base.glob("session-*")):
            try:
                private_directory(folder)
                data = read_json(folder / "session.json")
                if data.get("operation") == "apply" and data.get("status") == "applied":
                    options.append((folder, data))
            except Stop:
                continue
        require(options, "Nu există o aplicare confirmată cu backup local pentru restaurare.")
        for index, (folder, data) in enumerate(options, 1):
            self.say(str(index) + ". " + folder.name + " — TV " + str(data.get("ip", "?")))
        choice = self.ask("Numărul backupului (Enter = anulare): ").strip()
        require(choice.isdigit() and 1 <= int(choice) <= len(options), "Restaurare anulată.")
        selected = options[int(choice) - 1][0]
        self.say("Backup ales: " + str(selected))
        return selected

    def run(self, operation, ip, previous=None):
        ip = validate_ip(ip)
        self.start(operation, ip)
        try:
            metadata = self.connect()
            self.mark("preflight", metadata=metadata)
            self.say("TV: " + metadata["modelName"] + " / firmware " + metadata["firmwareVersion"] +
                     " / SDK " + metadata["sdkVersion"])
            if operation == "check":
                self.mark("checked", referenceMatches=True)
                self.say("Profil " + self.profile.upper() + " identificat; fișierele și redarea nu au fost testate.")
            elif operation == "apply":
                self.apply()
            elif operation == "restore":
                require(previous is not None, "Selectează un backup pentru restaurare.")
                self.restore(previous)
            else:
                raise Stop("Operație necunoscută.")
        except (Stop, OSError, ValueError, KeyboardInterrupt) as error:
            write_started = self.state.get("status") in (
                "apply-started", "apply-confirmed", "restore-started", "restore-confirmed")
            status = "needs-attention" if write_started or isinstance(error, (NeedsAttention, KeyboardInterrupt)) else "stopped"
            self.mark(status, lastStage=self.state.get("status"), errorType=type(error).__name__)
            raise


def main():
    if len(sys.argv) > 1:
        print("Pornește fără argumente: python3 install.py\nMeniu: verificare / reparare / restaurare.")
        return 0 if sys.argv[1:] in (["--help"], ["-h"]) else 2
    print("Apple TV pe LG — instalator experimental, verificat numai offline.")
    print("Repararea și restaurarea folosesc root temporar. Nu instalează root la pornire.")
    print("Corecția rămâne în aplicația originală; ai nevoie în continuare de cont și abonament.")
    print("1. Verifică televizorul (fără root)\n2. Repară Apple TV (backup + root temporar)\n"
          "3. Restaurează din backup\n0. Ieșire")
    installer = Installer()
    try:
        choice = input("Alege [0/1/2/3]: ").strip()
        if choice == "0":
            return 0
        require(choice in ("1", "2", "3"), "Alegere necunoscută.")
        prerequisites(installer.runner)
        previous = installer.choose_backup() if choice == "3" else None
        ip = validate_ip(input("IP-ul TV-ului din aplicația Developer Mode: "))
        installer.run({"1": "check", "2": "apply", "3": "restore"}[choice], ip, previous)
        return 0
    except (Stop, OSError, ValueError) as error:
        print("\nOprit: " + str(error), file=sys.stderr)
        if installer.folder:
            print("Păstrează privat: " + str(installer.folder), file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nOprit de utilizator. Dacă a pornit o operație TV, rezultatul trebuie verificat înainte de reluare.",
              file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    raise SystemExit(main())
