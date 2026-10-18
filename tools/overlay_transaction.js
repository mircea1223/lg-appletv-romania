// SPDX-License-Identifier: AGPL-3.0-or-later
/* One-shot transaction template for the tested LG C3 Apple TV 16.2.5 build.
 * The local bundle builder substitutes the stage and plan digest constants.
 * No firmware, database, account-data, native-identity or root-persistence writes.
 */
'use strict';
const fs = require('fs');
const crypto = require('crypto');
const stage = '__STAGE__';
const planSHA = '__PLAN_SHA__';
const app = '/media/cryptofs/apps/usr/palm/applications/com.apple.appletv';
const image = '/media/cryptofs/apps/usr/palm/data/images/com.apple.appletv/data.img';
const receiptParent = '/media/developer/temp';
const original = {
  'res/app.js': '43f0d73af0b75b92ff2f135dddede5cdbe38915233639c1b6e652930af284109',
  'res/main.js': '9e27c975bcdffa3caeff19d167d6c06f927d96d7f600482d02c1271d926ac713'
};
const patched = {
  'res/app.js': 'f4a751398e0e7a211556586d811798a94d25eaef27e4c85954bb88c92ff2dba3',
  'res/main.js': '6c3958261062f649785c551da25f89620173896721a63d0d08f7fa0fc77774f3'
};
const protectedFiles = [
  [app + '/AppleTV', 'd9f2da54d1c1e9ae7f9d14a8fecac13f963c99ee0eda40f0a5a52ac8f362f64a'],
  [app + '/appinfo.json', 'c0c9f72d4f70dbbc4f1bb23a4eb237a7a7a2a9331170d076afa7f5cd18d35ef8'],
  [app + '/res/4239.js', '14defc8cee346e6cb5a80ab8e881425c71fce20b2e5b5130145fff4b35985592'],
  [image, 'e80efaa39e92afe81b6218e6bb11d2c1e40d46b25f371d7cb18cf19807116221']
];
const paths = ['res/app.js', 'res/main.js'];
const inputNames = ['main.js', 'package.json', 'transaction.json', 'payload-app.js', 'payload-main.js'];
const backupNames = ['backup-app.js', 'backup-main.js'];
const base = stage.substring(stage.lastIndexOf('/') + 1);
const receiptPath = receiptParent + '/lg-appletv-ro-' + base + '-result.json';
const nofollow = fs.constants.O_NOFOLLOW;
let receiptFd;

function assert(value, message) { if (!value) throw Error(message); }
function hashBytes(bytes) { return crypto.createHash('sha256').update(bytes).digest('hex'); }
function sameKeys(object, keys) {
  return object && typeof object === 'object' && !Array.isArray(object) &&
    Object.keys(object).sort().join('|') === keys.slice().sort().join('|');
}
function regular(path, allowedUids) {
  const s = fs.lstatSync(path);
  assert(s.isFile() && !s.isSymbolicLink() && allowedUids.indexOf(s.uid) !== -1 &&
    (s.mode & 0o022) === 0 && fs.realpathSync(path) === path, 'Unsafe file: ' + path);
  return s;
}
function directory(path, allowedUids, forbidGroupWrite) {
  const s = fs.lstatSync(path);
  assert(s.isDirectory() && !s.isSymbolicLink() && allowedUids.indexOf(s.uid) !== -1 &&
    (s.mode & (forbidGroupWrite ? 0o022 : 0o002)) === 0 && fs.realpathSync(path) === path,
  'Unsafe directory: ' + path);
  return s;
}
function syncDir(path) {
  const fd = fs.openSync(path, fs.constants.O_RDONLY | nofollow | fs.constants.O_DIRECTORY);
  try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
}
function readChecked(path, allowedUids, maximum) {
  const before = regular(path, allowedUids);
  if (maximum !== undefined) assert(before.size <= maximum, 'Oversized input: ' + path);
  const fd = fs.openSync(path, fs.constants.O_RDONLY | nofollow);
  try {
    const opened = fs.fstatSync(fd);
    assert(opened.isFile() && opened.dev === before.dev && opened.ino === before.ino &&
      opened.size === before.size && allowedUids.indexOf(opened.uid) !== -1 &&
      (opened.mode & 0o022) === 0, 'Input identity changed: ' + path);
    const bytes = fs.readFileSync(fd);
    assert(bytes.length === opened.size, 'Input size changed: ' + path);
    return {path, info: opened, bytes, sha: hashBytes(bytes)};
  } finally { fs.closeSync(fd); }
}
function identityMatches(path, expected, allowedUids) {
  const now = regular(path, allowedUids);
  assert(now.dev === expected.dev && now.ino === expected.ino && now.size === expected.size,
    'File identity changed: ' + path);
  return now;
}
function mountPaths() {
  return fs.readFileSync('/proc/self/mountinfo', 'utf8').trim().split('\n').filter(Boolean).map(line => {
    const fields = line.split(' ');
    assert(fields.length >= 10, 'Malformed mount metadata');
    return fields[4].replace(/\\([0-7]{3})/g, (_, value) => String.fromCharCode(parseInt(value, 8)));
  });
}
function noStageMounts(path) {
  assert(!mountPaths().some(point => point === path || point.indexOf(path + '/') === 0),
    'Unexpected staging mount: ' + path);
}
function stageSnapshot(path, names, allowedUids, exactMode) {
  const info = directory(path, [0], true);
  if (exactMode !== undefined) assert((info.mode & 0o777) === exactMode, 'Unexpected staging mode');
  noStageMounts(path);
  assert(fs.readdirSync(path).sort().join('|') === names.slice().sort().join('|'),
    'Unexpected staging files: ' + path);
  const files = names.map(name => readChecked(path + '/' + name, allowedUids));
  return {path, info, files};
}
function verifySnapshot(snapshot) {
  const now = directory(snapshot.path, [0], true);
  assert(now.dev === snapshot.info.dev && now.ino === snapshot.info.ino, 'Staging directory changed');
  noStageMounts(snapshot.path);
  assert(fs.readdirSync(snapshot.path).sort().join('|') ===
    snapshot.files.map(file => file.path.substring(file.path.lastIndexOf('/') + 1)).sort().join('|'),
  'Staging contents changed');
  snapshot.files.forEach(file => {
    identityMatches(file.path, file.info, [0, 6303]);
    assert(readChecked(file.path, [0, 6303]).sha === file.sha, 'Staging contents changed');
  });
}
function deleteSnapshot(snapshot) {
  verifySnapshot(snapshot);
  for (const file of snapshot.files) {
    noStageMounts(snapshot.path);
    identityMatches(file.path, file.info, [0, 6303]);
    fs.unlinkSync(file.path);
  }
  const current = directory(snapshot.path, [0], true);
  assert(current.dev === snapshot.info.dev && current.ino === snapshot.info.ino &&
    fs.readdirSync(snapshot.path).length === 0, 'Staging changed before rmdir');
  noStageMounts(snapshot.path);
  fs.rmdirSync(snapshot.path);
  syncDir('/media/internal/downloads');
}
function createDurable(path, bytes, gid, mode, onCreate) {
  const fd = fs.openSync(path, fs.constants.O_WRONLY | fs.constants.O_CREAT |
    fs.constants.O_EXCL | nofollow, 0o600);
  try {
    if (onCreate) onCreate(fs.fstatSync(fd));
    fs.writeFileSync(fd, bytes);
    fs.fchownSync(fd, 0, gid);
    fs.fchmodSync(fd, mode);
    fs.fsyncSync(fd);
  } finally { fs.closeSync(fd); }
}
function guardProtected() {
  for (const pair of protectedFiles) {
    const value = readChecked(pair[0], [0]);
    assert(value.sha === pair[1], 'Original native identity/image or 4239.js changed');
  }
}
function guardOverlay() {
  const rows = fs.readFileSync('/proc/self/mountinfo', 'utf8').split('\n');
  const matching = rows.filter(line => line.split(' ')[4] === app &&
    line.indexOf(' - overlay ') !== -1 &&
    /(?:^|,)upperdir=\/media\/data\/data\/com\.apple\.appletv(?:,|$)/.test(line));
  assert(matching.length === 1 && /(?:^|,)rw(?:,|$)/.test(matching[0].split(' ')[5]),
    'Expected existing writable Apple TV overlay was not found');
  const s = directory(app + '/res', [0], false);
  assert(s.gid === 5000 && (s.mode & 0o777) === 0o775, 'Unexpected LG resource permissions');
}
function target(path) {
  const value = readChecked(path, [0], 16 * 1024 * 1024);
  assert(value.info.gid === 5000 && (value.info.mode & 0o777) === 0o644,
    'Unexpected resource ownership/mode');
  return value;
}
function matchingPids(main) {
  const result = [];
  for (const name of fs.readdirSync('/proc')) {
    if (!/^[0-9]+$/.test(name)) continue;
    try {
      const exe = fs.statSync('/proc/' + name + '/exe');
      if (exe.dev === main.dev && exe.ino === main.ino) result.push(Number(name));
    } catch (error) { if (error.code !== 'ENOENT' && error.code !== 'ESRCH') throw error; }
  }
  return result;
}
function signalMatching(main, signal) {
  const signalled = [];
  for (const pid of matchingPids(main)) {
    try {
      const exe = fs.statSync('/proc/' + pid + '/exe');
      if (exe.dev !== main.dev || exe.ino !== main.ino) continue;
      process.kill(pid, signal);
      if (signal === 'SIGTERM') {
        try {
          const still = fs.statSync('/proc/' + pid + '/exe');
          if (still.dev === main.dev && still.ino === main.ino) process.kill(pid, 'SIGCONT');
        } catch (error) { if (error.code !== 'ENOENT' && error.code !== 'ESRCH') throw error; }
      }
      signalled.push(pid);
    } catch (error) { if (error.code !== 'ENOENT' && error.code !== 'ESRCH') throw error; }
  }
  return signalled;
}
async function waitStopped(main, milliseconds) {
  const deadline = Date.now() + milliseconds;
  do {
    if (matchingPids(main).length === 0) return true;
    await new Promise(resolve => setTimeout(resolve, 200));
  } while (Date.now() < deadline);
  return matchingPids(main).length === 0;
}
function removeOwnTemp(entry, property) {
  const temporary = entry[property];
  if (!temporary || !temporary.info) return;
  let s;
  try { s = fs.lstatSync(temporary.path); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
  assert(s.isFile() && !s.isSymbolicLink() && s.uid === 0 &&
    s.dev === temporary.info.dev && s.ino === temporary.info.ino, 'Temporary file identity changed');
  fs.unlinkSync(temporary.path);
  syncDir(app + '/res');
}
function rollback(entry) {
  const current = target(entry.path);
  if (current.sha === entry.currentSHA256) return;
  assert(current.sha === entry.outputSHA256, 'Rollback refuses unrelated resource change');
  identityMatches(entry.backup.path, entry.backup.info, [0]);
  const backup = readChecked(entry.backup.path, [0], 16 * 1024 * 1024);
  assert(backup.sha === entry.currentSHA256 && (backup.info.mode & 0o777) === 0o600,
    'Rollback backup mismatch');
  entry.rollbackTemp = {path: entry.path + '.' + base + '.rollback'};
  createDurable(entry.rollbackTemp.path, backup.bytes, 5000, 0o644,
    info => { entry.rollbackTemp.info = info; });
  const now = target(entry.path);
  assert(now.sha === entry.outputSHA256 && now.info.dev === current.info.dev &&
    now.info.ino === current.info.ino, 'Rollback target changed');
  assert(target(entry.rollbackTemp.path).sha === entry.currentSHA256, 'Rollback temporary mismatch');
  fs.renameSync(entry.rollbackTemp.path, entry.path);
  syncDir(app + '/res');
  assert(target(entry.path).sha === entry.currentSHA256, 'Rollback verification failed');
}
function openReceipt() {
  // The tested C3 has this exact pre-existing shared temporary directory.
  // O_EXCL/O_NOFOLLOW and the held private descriptor protect the receipt write;
  // never create or change either global directory to make a different TV fit.
  const parent = directory('/media/developer', [0], false);
  assert(parent.gid === 0 && (parent.mode & 0o777) === 0o775,
    'Unexpected developer directory permissions');
  const temporary = fs.lstatSync(receiptParent);
  assert(temporary.isDirectory() && !temporary.isSymbolicLink() &&
    temporary.uid === 0 && temporary.gid === 0 && (temporary.mode & 0o777) === 0o777 &&
    fs.realpathSync(receiptParent) === receiptParent, 'Unexpected shared temporary directory');
  receiptFd = fs.openSync(receiptPath, fs.constants.O_WRONLY | fs.constants.O_CREAT |
    fs.constants.O_EXCL | nofollow, 0o600);
}
function finishReceipt(value) {
  if (receiptFd === undefined) openReceipt();
  const bytes = Buffer.from(JSON.stringify(value, null, 2) + '\n');
  let written = 0;
  while (written < bytes.length) {
    const count = fs.writeSync(receiptFd, bytes, written, bytes.length - written, written);
    assert(count > 0, 'Unable to write result');
    written += count;
  }
  fs.ftruncateSync(receiptFd, bytes.length);
  fs.fchmodSync(receiptFd, 0o600);
  fs.fsyncSync(receiptFd);
  fs.fchownSync(receiptFd, 6303, 5000);
  fs.fsyncSync(receiptFd);
  syncDir(receiptParent);
}

async function run() {
  let root = false, committed = false, exitCode = 1, plan, exportSnapshot;
  const entries = [], rollbackErrors = [];
  const actions = {terminated: 0, forced: 0, exportStageRemoved: false, ownStageRemoved: false};
  try {
    assert(process.getuid() === 0, 'Root access was not obtained');
    root = true;
    assert(typeof nofollow === 'number' && typeof fs.constants.O_DIRECTORY === 'number', 'Required safe file APIs unavailable');
    assert(/^\/media\/internal\/downloads\/lg-appletv-ro-[A-Za-z0-9_-]{8,100}$/.test(stage) &&
      __dirname === stage && /^[0-9a-f]{64}$/.test(planSHA), 'Unexpected execution context');
    process.umask(0o077);
    directory('/media/internal/downloads', [0], true);
    stageSnapshot(stage, inputNames, [0]);
    const planInput = readChecked(stage + '/transaction.json', [0], 16384);
    assert(planInput.sha === planSHA, 'Transaction plan hash mismatch');
    plan = JSON.parse(planInput.bytes.toString('utf8'));
    const allowedPlanKeys = plan.cleanupExport === undefined ? ['kind', 'mode', 'files'] :
      ['kind', 'mode', 'files', 'cleanupExport'];
    assert(sameKeys(plan, allowedPlanKeys) && plan.kind === 'lg-appletv-ro-overlay-v1' &&
      (plan.mode === 'apply' || plan.mode === 'restore') && Array.isArray(plan.files) &&
      plan.files.length === 2, 'Unexpected transaction schema');
    if (plan.cleanupExport !== undefined) {
      const cleanup = plan.cleanupExport;
      assert(plan.mode === 'apply' && sameKeys(cleanup, ['stage', 'archiveSHA256']) &&
        /^\/media\/internal\/downloads\/lg-appletv-ro-export-[A-Za-z0-9_-]{8,100}$/.test(cleanup.stage) &&
        cleanup.stage !== stage && /^[0-9a-f]{64}$/.test(cleanup.archiveSHA256), 'Invalid export cleanup request');
      exportSnapshot = stageSnapshot(cleanup.stage,
        ['main.js', 'package.json', 'transaction.json', 'apple-tv-original.tar', 'result.json'], [0, 6303], 0o711);
      const archive = exportSnapshot.files.find(file => file.path === cleanup.stage + '/apple-tv-original.tar');
      const report = exportSnapshot.files.find(file => file.path === cleanup.stage + '/result.json');
      assert(report.bytes.length <= 16384 && archive.sha === cleanup.archiveSHA256, 'Export archive verification failed');
      const result = JSON.parse(report.bytes.toString('utf8'));
      assert(result.status === 'success' && result.kind === 'lg-appletv-ro-export-v1' &&
        result.archiveSHA256 === cleanup.archiveSHA256 &&
        result.archivePath === cleanup.stage + '/apple-tv-original.tar', 'Export receipt mismatch');
    }
    guardProtected(); guardOverlay();
    for (let index = 0; index < paths.length; index++) {
      const spec = plan.files[index], relative = paths[index];
      assert(sameKeys(spec, ['path', 'stagedName', 'currentSHA256', 'outputSHA256']) &&
        spec.path === relative && spec.stagedName === inputNames[index + 3] &&
        spec.currentSHA256 === (plan.mode === 'apply' ? original[relative] : patched[relative]) &&
        spec.outputSHA256 === (plan.mode === 'apply' ? patched[relative] : original[relative]),
      'Unexpected resource mapping or hashes');
      const current = target(app + '/' + relative);
      const payload = readChecked(stage + '/' + spec.stagedName, [0], 16 * 1024 * 1024);
      assert(current.sha === spec.currentSHA256 && payload.sha === spec.outputSHA256,
        'Source or current application version mismatch');
      entries.push({path: current.path, before: current.info, currentSHA256: spec.currentSHA256,
        outputSHA256: spec.outputSHA256, payload,
        backup: {path: stage + '/' + backupNames[index]},
        temporary: {path: current.path + '.' + base + '.new'}});
    }
    // Reserve the result name before stopping the app or writing application resources.
    openReceipt();
    for (const entry of entries) {
      const current = target(entry.path);
      assert(current.sha === entry.currentSHA256 && current.info.dev === entry.before.dev &&
        current.info.ino === entry.before.ino, 'Resource changed before backup');
      createDurable(entry.backup.path, current.bytes, 0, 0o600);
      const backup = readChecked(entry.backup.path, [0], 16 * 1024 * 1024);
      assert(backup.sha === entry.currentSHA256 && (backup.info.mode & 0o777) === 0o600,
        'Backup verification failed');
      entry.backup.info = backup.info;
    }
    syncDir(stage);
    stageSnapshot(stage, inputNames.concat(backupNames), [0]);
    const main = regular(app + '/AppleTV', [0]);
    actions.terminated = signalMatching(main, 'SIGTERM').length;
    if (!(await waitStopped(main, 8000))) {
      actions.forced = signalMatching(main, 'SIGKILL').length;
      assert(await waitStopped(main, 2000), 'Original Apple TV process could not be stopped');
    }
    guardProtected(); guardOverlay();
    assert(matchingPids(main).length === 0, 'Original application restarted');
    for (const entry of entries) {
      const current = target(entry.path);
      assert(current.sha === entry.currentSHA256 && current.info.dev === entry.before.dev &&
        current.info.ino === entry.before.ino, 'Resource changed before staging');
      identityMatches(entry.payload.path, entry.payload.info, [0]);
      assert(readChecked(entry.payload.path, [0]).sha === entry.outputSHA256, 'Payload changed');
      createDurable(entry.temporary.path, entry.payload.bytes, 5000, 0o644,
        info => { entry.temporary.info = info; });
      assert(target(entry.temporary.path).sha === entry.outputSHA256, 'Temporary payload mismatch');
    }
    syncDir(app + '/res');
    for (const entry of entries) {
      assert(matchingPids(main).length === 0, 'Original application restarted before commit');
      const current = target(entry.path);
      assert(current.sha === entry.currentSHA256 && current.info.dev === entry.before.dev &&
        current.info.ino === entry.before.ino, 'Resource changed before rename');
      identityMatches(entry.temporary.path, Object.assign({}, entry.temporary.info,
        {size: entry.payload.bytes.length}), [0]);
      assert(target(entry.temporary.path).sha === entry.outputSHA256, 'Temporary payload changed');
      fs.renameSync(entry.temporary.path, entry.path);
      syncDir(app + '/res');
      assert(target(entry.path).sha === entry.outputSHA256, 'Installed payload mismatch');
    }
    guardProtected(); guardOverlay();
    entries.forEach(entry => assert(target(entry.path).sha === entry.outputSHA256, 'Final resource verification failed'));
    committed = true;
    // Cleanup is strictly after commit. A cleanup failure never rolls the working app back.
    const ownSnapshot = stageSnapshot(stage, inputNames.concat(backupNames), [0]);
    verifySnapshot(ownSnapshot);
    if (exportSnapshot) { verifySnapshot(exportSnapshot); deleteSnapshot(exportSnapshot); actions.exportStageRemoved = true; }
    deleteSnapshot(ownSnapshot); actions.ownStageRemoved = true;
    finishReceipt({kind: 'lg-appletv-ro-overlay-result-v1', status: 'success', mode: plan.mode,
      committed: true, appId: 'com.apple.appletv', modifiedFiles: paths,
      outputSHA256: entries.reduce((out, entry) => {
        out[entry.path.substring(app.length + 1)] = entry.outputSHA256; return out;
      }, {}),
      originalNativeIdentityUnchanged: true, originalImageUnchanged: true, original4239Unchanged: true,
      appDataRead: false, databaseWritesPerformed: false, installedPersistentRoot: false, actions});
    console.log('Apple TV ' + plan.mode + ' completed: ' + receiptPath);
    exitCode = 0;
  } catch (error) {
    if (!committed) {
      for (const entry of entries.slice().reverse()) {
        try { removeOwnTemp(entry, 'temporary'); if (entry.backup.info) rollback(entry); }
        catch (rollbackError) { rollbackErrors.push(rollbackError.message); }
        try { removeOwnTemp(entry, 'rollbackTemp'); }
        catch (cleanupError) { rollbackErrors.push(cleanupError.message); }
      }
    }
    if (root && /^\/media\/internal\/downloads\/lg-appletv-ro-[A-Za-z0-9_-]{8,100}$/.test(stage)) {
      try {
        finishReceipt({kind: 'lg-appletv-ro-overlay-result-v1', status: 'failed', mode: plan && plan.mode,
          committed, error: error.message, rollbackErrors, stageRetained: !actions.ownStageRemoved,
          cleanupExportStageRetained: !!exportSnapshot && !actions.exportStageRemoved,
          installedPersistentRoot: false, databaseWritesPerformed: false, appDataRead: false, actions});
      } catch (reportError) { console.error('Unable to export result: ' + reportError.message); }
    }
    console.error('Apple TV transaction failed: ' + error.message);
  } finally {
    if (receiptFd !== undefined) { try { fs.closeSync(receiptFd); } catch (_) {} }
    process.exit(exitCode);
  }
}
module.exports = {run};
