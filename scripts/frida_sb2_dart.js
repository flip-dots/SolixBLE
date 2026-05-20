/*
 * Script name   : frida_sb2_dart.js
 * Description   : Frida script to analyze BLE traffic of the
 *                 Anker app's Dart AOT code in libapp.so.
 * Author        : jul1an-s
 * Date          : 19/05/26
 *
 * License       : MIT
 * Revision      : 1.0.0
 *
 * App version   : This probably only works with Anker app version 3.18.0
 * 
 * For addtional app versions you need to analyze the app with apktool and blutter
 *  
 * A one-shot AES module scan runs at load + on first BLE RX as a sanity check
 * that libcrypto + libapp are present.
 *
 * libapp.so offsets are APK-version-specific. Use apktool and blutter 
 * to determine the correct addresses for your version.
 *
 * Header layout, BLE hook style, and anti-tamper pattern adapted from frida.js
 * by Harvey Lelliott (@flip-dots), MIT-licensed.
 * 
 * Known issue: plaintext parsing is not implemented. Use the captured
 * session key + IV to decrypt the encrypted payloads externally.
*/

// Utilities

function log(msg) {
    console.log(msg);
}

function toHex(byteArray) {
    if (!byteArray) return "null";
    try {
        var result = "";
        for (var i = 0; i < byteArray.length; i++) {
            result += ('0' + (byteArray[i] & 0xFF).toString(16)).slice(-2);
        }
        return result;
    } catch (e) {
        return "Error parsing byte array";
    }
}

function hexdumpNative(ptr, len) {
    if (ptr.isNull()) return "null";
    try {
        var bytes = ptr.readByteArray(len);
        if (!bytes) return "null";
        var arr = new Uint8Array(bytes);
        var hex = "";
        for (var i = 0; i < arr.length; i++) {
            hex += ('0' + arr[i].toString(16)).slice(-2);
        }
        return hex;
    } catch (e) {
        return "read error: " + e;
    }
}

// Diagnostic tracking - structured tags ([HOOK-ATTACHED], [HOOK-FIRED],
// [HOOK-FIRE-SUMMARY]) for grepping a session log.

var attachedHooks = [];
var hookFireCounts = {};
var hookFiredFirst = {};

function noteAttached(name) {
    attachedHooks.push(name);
    log("[HOOK-ATTACHED] " + name);
}

function noteFired(name) {
    hookFireCounts[name] = (hookFireCounts[name] || 0) + 1;
    if (!hookFiredFirst[name]) {
        hookFiredFirst[name] = true;
        log("[HOOK-FIRED] first fire: " + name);
    }
}

// Periodic firing summary - every 15s. Quiet if nothing changed.
var lastSummarySnapshot = {};
setInterval(function() {
    var keys = Object.keys(hookFireCounts);
    if (keys.length === 0) {
        log("[HOOK-FIRE-SUMMARY] " + attachedHooks.length + " hooks attached, 0 fired so far");
        return;
    }
    var changed = false;
    var snapshot = {};
    for (var i = 0; i < keys.length; i++) {
        snapshot[keys[i]] = hookFireCounts[keys[i]];
        if (lastSummarySnapshot[keys[i]] !== hookFireCounts[keys[i]]) changed = true;
    }
    if (changed) {
        log("[HOOK-FIRE-SUMMARY] " + JSON.stringify(snapshot));
        lastSummarySnapshot = snapshot;
    }
}, 15000);

// AES library identification - scan loaded modules for the AES S-box, the
// ARMv8 AESE/AESD instruction signature, and the ChaCha20 constant. Runs
// once at script load and again on the first BLE RX (to catch libs that
// load on demand).
var aesScanDone = false;
var prevModuleSet = null;
var rescanDone = false;
function maybeRescanCrypto() {
    if (rescanDone) return;
    rescanDone = true;
    log("\n[+] --- AES MODULE RESCAN (BLE session detected) ---");
    try {
        var current = {};
        Process.enumerateModules().forEach(function(m) { current[m.name] = m.base.toString(); });
        if (prevModuleSet) {
            var newMods = [];
            Object.keys(current).forEach(function(name) {
                if (!prevModuleSet[name]) newMods.push(name);
            });
            if (newMods.length === 0) {
                log("[AES-RESCAN] no new modules loaded since startup scan");
            } else {
                log("[AES-RESCAN] " + newMods.length + " new modules loaded since startup:");
                newMods.forEach(function(n) { log("[AES-RESCAN]   " + n); });
            }
        }
        // Re-arm and re-run the AES/ChaCha scan
        aesScanDone = false;
        scanModulesForAES();
    } catch (e) {
        log("[AES-RESCAN] error: " + e + (e.stack ? "\n  stack:\n" + e.stack : ""));
    }
}

function scanModulesForAES() {
    // Snapshot module set on first run so the rescan can diff against it.
    if (prevModuleSet === null) {
        try {
            prevModuleSet = {};
            Process.enumerateModules().forEach(function(m) { prevModuleSet[m.name] = m.base.toString(); });
        } catch (e) {}
    }
    if (aesScanDone) return;
    aesScanDone = true;

    var SBOX_PATTERN = "63 7c 77 7b f2 6b 6f c5 30 01 67 2b fe d7 ab 76";
    var AES_INSTR_PATTERN = "28 4e";
    // ChaCha20 initial state constant "expand 32-byte k"
    var CHACHA20_CONST = "65 78 70 61 6e 64 20 33 32 2d 62 79 74 65 20 6b";

    log("\n[+] --- AES MODULE SCAN ---");
    var modules;
    try {
        modules = Process.enumerateModules();
    } catch (e) {
        log("[AES-SCAN] enumerateModules failed: " + e);
        return;
    }
    log("[AES-SCAN] " + modules.length + " loaded modules");

    var hits = [];
    modules.forEach(function(mod) {
        try {
            var sbox = 0, instr = 0, chacha = 0;
            var ranges;
            try { ranges = mod.enumerateRanges('r--'); } catch (e) { return; }
            ranges.forEach(function(r) {
                try { sbox   += Memory.scanSync(r.base, r.size, SBOX_PATTERN).length; } catch (e) {}
                try { instr  += Memory.scanSync(r.base, r.size, AES_INSTR_PATTERN).length; } catch (e) {}
                try { chacha += Memory.scanSync(r.base, r.size, CHACHA20_CONST).length; } catch (e) {}
            });
            if (sbox > 0 || instr > 20 || chacha > 0) {
                hits.push({ name: mod.name, base: mod.base.toString(), size: mod.size,
                            sbox: sbox, instr: instr, chacha: chacha });
            }
        } catch (e) {}
    });

    if (hits.length === 0) {
        log("[AES-SCAN] NO libraries contain crypto code (suspicious - at minimum libcrypto.so should hit)");
        return;
    }
    // Sort by combined evidence (SBOX heavily weighted; ChaCha20 const is also a strong signal)
    hits.sort(function(a, b) {
        return (b.sbox * 1000 + b.chacha * 1000 + b.instr) - (a.sbox * 1000 + a.chacha * 1000 + a.instr);
    });
    log("[AES-SCAN] " + hits.length + " libraries contain crypto code (sorted by evidence):");
    hits.forEach(function(h) {
        log("[AES-SCAN]   " + h.name + "  base=" + h.base + "  size=" + h.size +
            "  SBOX=" + h.sbox + "  AES_instr=" + h.instr + "  ChaCha20=" + h.chacha);
    });
}


// Hook installers

var installed = { antitamper: false, ble: false, dartCrypto: false };

function installAntiTamper() {
    if (installed.antitamper) return;
    Java.perform(function() {
        try {
            var System = Java.use('java.lang.System');
            var AndroidProcess = Java.use('android.os.Process');
            System.exit.implementation = function(code) {
                noteFired("System.exit");
                log("[!] Intercepted exit (" + code + ")");
            };
            AndroidProcess.killProcess.implementation = function(pid) {
                noteFired("Process.killProcess");
                log("[!] Intercepted killProcess for PID: " + pid);
            };
            installed.antitamper = true;
            noteAttached("anti-tamper (System.exit, Process.killProcess)");
            // Anti-tamper-safe to scan loaded modules for AES code.
            scanModulesForAES();
        } catch (e) {
            log("[-] anti-tamper hook error: " + e);
        }
    });
}

function installBleHooks() {
    if (installed.ble) return;
    Java.perform(function() {
        try {
            var BluetoothGatt = Java.use('android.bluetooth.BluetoothGatt');
            var BluetoothGattCharacteristic = Java.use('android.bluetooth.BluetoothGattCharacteristic');

            BluetoothGatt.writeCharacteristic.overloads.forEach(function(overload) {
                overload.implementation = function() {
                    noteFired("BluetoothGatt.writeCharacteristic");
                    var char = arguments[0];
                    var data = (arguments.length >= 2) ? arguments[1] : char.getValue();
                    var uuid = char.getUuid().toString();
                    // Filter to the Anker service characteristic UUIDs (per past captures: contains "8c850")
                    if (uuid.indexOf("8c850") >= 0) {
                        log("\n[BLE WRITE] UUID: " + uuid);
                        log("Data (Hex): " + toHex(data));
                    }
                    return overload.apply(this, arguments);
                };
            });

            BluetoothGattCharacteristic.setValue.overloads.forEach(function(overload) {
                overload.implementation = function() {
                    noteFired("BluetoothGattCharacteristic.setValue");
                    var uuid = this.getUuid().toString();
                    var value = arguments[0];
                    if (uuid.indexOf("8c850") >= 0 && value !== null && typeof value === 'object') {
                        log("\n[BLE NOTIFY] UUID: " + uuid);
                        log("Data (Hex): " + toHex(value));
                        // First BLE RX - rescan modules for late-loaded crypto libs.
                        maybeRescanCrypto();
                    }
                    return overload.apply(this, arguments);
                };
            });

            installed.ble = true;
            noteAttached("android.bluetooth.BluetoothGatt.writeCharacteristic + BluetoothGattCharacteristic.setValue (filter 8c850)");
        } catch (e) {
            log("[-] BLE hook error: " + e);
        }
    });
}


// Dart AOT hooks (libapp.so via blutter offsets, APK-version-specific)

var dartHeapBase = null;
var DART_CID_POS = 12;
var DART_CID_MASK = 0xfffff;
// CIDs from blutter_frida.js class table (Dart 3.4.4, this libapp.so):
var DART_CID_ARRAY         = 89;   // immutable List
var DART_CID_GROWABLE_LIST = 91;   // mutable List
var DART_CID_STRING        = 93;
var DART_CID_TWO_BYTE_STRING = 94;
var DART_CID_UINT8LIST     = 115;  // _Uint8List
var DART_CID_NULL          = 170;

function dartInit(context) { if (dartHeapBase === null) dartHeapBase = context.x28.shl(32); }
function dartDecompress(tptr) { return dartHeapBase.add(tptr.toInt32()); }
function dartIsHeap(tptr) { return (tptr.toInt32() & 1) === 1; }
function dartGetCid(ptr) { return (ptr.readU32() >>> DART_CID_POS) & DART_CID_MASK; }

// Read up to 'maxBytes' bytes from a List/GrowableList of int. Each element
// is a Smi stored as a 4-byte compressed pointer (Dart 3.4 ARM64 AOT); raw
// 32-bit value has low bit=0 and value = raw >> 1.
function readListInt(ptr, len, maxBytes) {
    var n = Math.min(len, maxBytes);
    var hex = "";
    try {
        for (var i = 0; i < n; i++) {
            var raw = ptr.add(16 + i * 4).readU32();
            var b = (raw >>> 1) & 0xff;
            hex += ('0' + b.toString(16)).slice(-2);
        }
        if (len > maxBytes) hex += "...";
        return hex;
    } catch (e) {
        return "(readListInt err: " + e + ")";
    }
}

function dartReadObject(tptr) {
    try {
        if (!dartIsHeap(tptr)) return { type: "Smi", value: tptr.toInt32() >> 1 };
        var ptr = dartDecompress(tptr).sub(1);
        var cid = dartGetCid(ptr);
        if (cid === DART_CID_NULL) return { type: "Null" };
        if (cid === DART_CID_STRING) {
            var len = ptr.add(8).readU32() >> 1;
            return { type: "String", value: ptr.add(16).readUtf8String(len) };
        }
        if (cid === DART_CID_TWO_BYTE_STRING) {
            var len = ptr.add(8).readU32() >> 1;
            return { type: "TwoByteString", value: ptr.add(16).readUtf16String(len) };
        }
        if (cid === DART_CID_UINT8LIST) {
            var len = ptr.add(20).readU32() >> 1;
            var data = ptr.add(24);
            var hex = "";
            for (var i = 0; i < Math.min(len, 512); i++) {
                hex += ('0' + data.add(i).readU8().toString(16)).slice(-2);
            }
            if (len > 512) hex += "...";
            return { type: "Uint8List", length: len, value: hex };
        }
        if (cid === DART_CID_GROWABLE_LIST || cid === DART_CID_ARRAY) {
            // length stored at offset 12 (per blutter lenOffset)
            var len = ptr.add(12).readU32() >> 1;
            if (cid === DART_CID_ARRAY) {
                // _List (cid 89): elements stored inline at ptr+16. Decoder works.
                return { type: "List", length: len, value: readListInt(ptr, len, 512) };
            }
            // _GrowableList (cid 91): offset 16 holds a tagged pointer to the
            // backing Array. Follow it if we can; if the indirection fails do
            // NOT fall back to reading ptr+16 directly — that reads pointer
            // and header bytes as if they were Smi-encoded data and emits
            // adjacent-memory garbage that pollutes the log.
            try {
                var dataPtr = ptr.add(16).readU32();
                if (dataPtr & 1) {
                    var backing = dartDecompress(ptr.add(16).readU64()).sub(1);
                    return { type: "GrowableList", length: len, value: readListInt(backing, len, 512) };
                }
            } catch (e) {}
            return { type: "GrowableList", length: len, value: null };
        }
        return { type: "cid:" + cid, value: null };
    } catch (e) {
        return { type: "error", value: e.toString() };
    }
}

function dartFormatObj(obj) {
    if (obj.type === "String") return '"' + obj.value + '"';
    if (obj.type === "Uint8List") return "Uint8List(" + obj.length + "): " + obj.value;
    if (obj.type === "Smi") return "int:" + obj.value;
    if (obj.value !== null) return obj.type + "=" + obj.value;
    return obj.type;
}

// Dart function offsets in libapp.so, derived from blutter analysis.
// setAesKey/setAesIV signature is (bleMac, keyBytes) so the key/iv is in x3.
// AesHelper::aesGcm{Encrypt,Decrypt} are static, args in x2 + x3.
var DART_HOOK_SPECS = [
    // BLE session lifecycle
    { name: "ZXBleConfer::startZXBleConfer",          off: 0x1ecd430 },
    { name: "ZXBleConfer::sendConnectCommand",        off: 0x1ecd958 },
    { name: "BleConfer::addBleConnectStatusListener", off: 0x3641d5c },
    { name: "SecureEcdhConfer::startConfer",          off: 0x3644e7c },
    // Session key/IV storage
    { name: "BleInfoHelper::setAesKey",               off: 0x1d45ddc, decodeArg: 3 },
    { name: "BleInfoHelper::setAesIV",                off: 0x1d45cf0, decodeArg: 3 },
    { name: "BleInfoHelper::getAesKey",               off: 0x199fec0, decodeRet: true },
    { name: "BleInfoHelper::getAesIV",                off: 0x199ff18, decodeRet: true },
    // GCM path used for session-encrypted SB2 commands (405e, 4022, 4027)
    { name: "AesHelper::aesGcmEncrypt",               off: 0x199ffc8, decodeArg: 2, decodeArg2: 3 },
    { name: "AesHelper::aesGcmDecrypt",               off: 0x1ea6e30, decodeArg: 2, decodeArg2: 3 }
];

// Cache of last decoded retval per spec.name, used to suppress duplicate
// enter+leave logs (getAesKey/getAesIV fire many times back-to-back).
var lastDecodedRet = {};

function installDartCryptoHooks() {
    if (installed.dartCrypto) return false;
    var mod = Process.findModuleByName('libapp.so');
    if (!mod) return false;
    var libapp = mod.base;
    log("\n[+] --- LIBAPP.SO LOADED ---");
    log("Base address: " + libapp);

    // Decode a Dart tagged-pointer register; falls back to raw hex.
    function tryDecodeArg(ctx, regName) {
        var raw = ctx[regName];
        try {
            dartInit(ctx);
            var obj = dartReadObject(raw);
            if (obj && obj.type === "Uint8List") {
                return regName + "=Uint8List(" + obj.length + "B):" + obj.value;
            }
            if (obj && (obj.type === "GrowableList" || obj.type === "List")) {
                if (obj.value === null) {
                    return regName + "=" + obj.type + "(" + obj.length + "B)<bytes-unreadable>";
                }
                return regName + "=" + obj.type + "(" + obj.length + "B):" + obj.value;
            }
            if (obj && obj.type === "String") {
                return regName + '=String:"' + obj.value + '"';
            }
            if (obj && obj.type === "Smi") {
                return regName + "=Smi:" + obj.value;
            }
            if (obj && obj.type === "Null") {
                return regName + "=Null";
            }
            // obj.type already starts with "cid:" for unknown types - don't double-prefix
            return regName + "=" + raw + " (" + (obj ? obj.type : "?") + ")";
        } catch (e) {
            return regName + "=" + raw;
        }
    }

    var count = 0;
    DART_HOOK_SPECS.forEach(function(spec) {
        try {
            Interceptor.attach(libapp.add(spec.off), {
                onEnter: function() {
                    noteFired("libapp.so:" + spec.name);
                    var c = this.context;
                    var parts = ["x1=" + c.x1];
                    var decodedRegs = {};
                    if (spec.decodeArg !== undefined) {
                        var reg = "x" + spec.decodeArg;
                        parts.push(tryDecodeArg(c, reg));
                        decodedRegs[reg] = true;
                    }
                    if (spec.decodeArg2 !== undefined) {
                        var reg2 = "x" + spec.decodeArg2;
                        parts.push(tryDecodeArg(c, reg2));
                        decodedRegs[reg2] = true;
                    }
                    ["x2","x3","x4"].forEach(function(r) {
                        if (!decodedRegs[r]) parts.push(r + "=" + c[r]);
                    });
                    var line = "[DART-FN] " + spec.name + "  " + parts.join("  ");
                    // Defer for decodeRet so onLeave can suppress unchanged pairs.
                    if (spec.decodeRet) {
                        this._enterLine = line;
                    } else {
                        log(line);
                    }
                },
                onLeave: function(retval) {
                    if (!spec.decodeRet) return;
                    var retLine, cacheKey;
                    try {
                        var c = this.context;
                        dartInit(c);
                        var obj = dartReadObject(ptr(retval.toString()));
                        if (obj && obj.type === "Uint8List") {
                            cacheKey = "u8:" + obj.value;
                            retLine = "[DART-FN] " + spec.name + "  → Uint8List(" + obj.length + "B): " + obj.value;
                        } else if (obj && (obj.type === "List" || obj.type === "GrowableList")) {
                            cacheKey = obj.type + ":" + (obj.value === null ? "<unreadable>:" + obj.length : obj.value);
                            if (obj.value === null) {
                                retLine = "[DART-FN] " + spec.name + "  → " + obj.type + "(" + obj.length + "B)<bytes-unreadable>";
                            } else {
                                retLine = "[DART-FN] " + spec.name + "  → " + obj.type + "(" + obj.length + "B): " + obj.value;
                            }
                        } else if (obj && obj.type === "String") {
                            cacheKey = "s:" + obj.value;
                            retLine = "[DART-FN] " + spec.name + '  → String:"' + obj.value + '"';
                        } else {
                            cacheKey = "raw:" + retval + ":" + (obj ? obj.type : "?");
                            retLine = "[DART-FN] " + spec.name + "  → " + retval + " (cid:" + (obj ? obj.type : "?") + ")";
                        }
                    } catch (e) {
                        cacheKey = "err:" + retval + ":" + e;
                        retLine = "[DART-FN] " + spec.name + "  → " + retval + " (decode err: " + e + ")";
                    }
                    if (lastDecodedRet[spec.name] === cacheKey) return;
                    lastDecodedRet[spec.name] = cacheKey;
                    if (this._enterLine) log(this._enterLine);
                    log(retLine);
                }
            });
            noteAttached("libapp.so:" + spec.name + " @ 0x" + spec.off.toString(16));
            count++;
        } catch (e) {
            log("[-] failed to hook " + spec.name + ": " + e);
        }
    });

    installed.dartCrypto = true;
    log("[+] installed " + count + " Dart hooks in libapp.so");
    return count > 0;
}

// Hook orchestration - ijiami delays DEX unpacking and lib loading, so we
// install framework hooks immediately and poll for libapp.so.

setImmediate(function() {
    installAntiTamper();
    installBleHooks();
});

// Poll for libapp.so load; one-shot setTimeout can fire too early.
(function() {
    var attempts = 0;
    var maxAttempts = 60;
    var poller = setInterval(function() {
        attempts++;
        if (!installed.dartCrypto) installDartCryptoHooks();
        if (installed.dartCrypto) {
            clearInterval(poller);
            log("[+] all native hooks installed");
        } else if (attempts >= maxAttempts) {
            clearInterval(poller);
            log("[*] native hook polling timeout. Missing: libapp.so Dart");
        }
    }, 1000);
})();


// RPC exports - call from a frida CLI session:
//   await rpc.exports.summary()    // hooks attached + fire counts
//   await rpc.exports.aesscan()    // re-run the module AES scan

rpc.exports = {
    summary: function() {
        return {
            script: "frida_sb2_dart.js",
            attached: attachedHooks,
            fired: hookFireCounts
        };
    },
    aesscan: function() {
        aesScanDone = false;
        scanModulesForAES();
        return "see [AES-SCAN] lines in log";
    }
};