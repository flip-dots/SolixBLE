/*
 * Script name   : frida.js
 * Description   : Frida script for preventing exit, extracting shared preferences, and tracing crypto/BLE with timestamps
 * Author        : Harvey Lelliott (@flip-dots) / Enhanced
 * Date          : 23/03/26
 * * License       : MIT
 * Revision      : 1.1.1
 */

// --- UTILITY FUNCTIONS ---

// Custom logger to automatically prepend timestamps
function log(msg) {
    var t = new Date();
    var timestamp = t.getHours().toString().padStart(2, '0') + ':' +
                    t.getMinutes().toString().padStart(2, '0') + ':' +
                    t.getSeconds().toString().padStart(2, '0') + '.' +
                    t.getMilliseconds().toString().padStart(3, '0');

    // Handle formatting for messages that start with a newline
    if (typeof msg === 'string' && msg.startsWith('\n')) {
        console.log('\n[' + timestamp + '] ' + msg.substring(1));
    } else {
        console.log('[' + timestamp + '] ' + msg);
    }
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

function printStackTrace(name) {
    var Log = Java.use("android.util.Log");
    var Exception = Java.use("java.lang.Exception");
    log(Log.getStackTraceString(Exception.$new(name)));
}

// --- LOADED MODULES ---
setImmediate(function() {
    log("\n--- Loaded Modules ---");
    Process.enumerateModules().forEach(function(module) {
        // Filter out standard Android system libraries to reduce noise
        if (!module.name.startsWith("libandroid") && !module.name.startsWith("libc.") && !module.path.includes("/system/")) {
            log("Name: " + module.name + " | Base: " + module.base);
        }
    });
    log("----------------------");
});

// --- SHARED PREFERENCES ---
setImmediate(function() {
    Java.perform(function() {
        var contextWrapper = Java.use("android.content.ContextWrapper");
        contextWrapper.getSharedPreferences.overload('java.lang.String', 'int').implementation = function(var0, var1) {
            log("[*] getSharedPreferences called with name: " + var0 + " and mode: " + var1);
            var sharedPreferences = this.getSharedPreferences(var0, var1);
            return sharedPreferences;
        };

        var sharedPreferencesEditor = Java.use("android.app.SharedPreferencesImpl$EditorImpl");
        sharedPreferencesEditor.putString.overload('java.lang.String', 'java.lang.String').implementation = function(var0, var1) {
            log("[*] Added a new String value to SharedPreferences with key: " + var0 + " and value " + var1);
            var editor = this.putString(var0, var1);
            return editor;
        }

        sharedPreferencesEditor.putBoolean.overload('java.lang.String', 'boolean').implementation = function(var0, var1) {
            log("[*] Added a new boolean value to SharedPreferences with key: " + var0 + " and value " + var1);
            var editor = this.putBoolean(var0, var1);
            return editor;
        }

        sharedPreferencesEditor.putFloat.overload('java.lang.String', 'float').implementation = function(var0, var1) {
            log("[*] Added a new float value to SharedPreferences with key: " + var0 + " and value " + var1);
            var editor = this.putFloat(var0, var1);
            return editor;
        }

        sharedPreferencesEditor.putInt.overload('java.lang.String', 'int').implementation = function(var0, var1) {
            log("[*] Added a new int value to SharedPreferences with key: " + var0 + " and value " + var1);
            var editor = this.putInt(var0, var1);
            return editor;
        }

        sharedPreferencesEditor.putLong.overload('java.lang.String', 'long').implementation = function(var0, var1) {
            log("[*] Added a new long value to SharedPreferences with key: " + var0 + " and value " + var1);
            var editor = this.putLong(var0, var1);
            return editor;
        }

        sharedPreferencesEditor.putStringSet.overload('java.lang.String', 'java.util.Set').implementation = function(var0, var1) {
            log("[*] Added a new string set to SharedPreferences with key: " + var0 + " and value " + var1);
            var editor = this.putStringSet(var0, var1);
            return editor;
        }

        var sharedPreferences = Java.use("android.app.SharedPreferencesImpl");
        sharedPreferences.getString.overload('java.lang.String', 'java.lang.String').implementation = function(var0, var1) {
            log("[*] Getting string value from SharedPreferences with key: " + var0 + " and value " + var1);
            var stringVal = this.getString(var0, var1);
            return stringVal;
        }
    });
});

// --- ANTI-TAMPER BYPASS ---
setImmediate(function() {
    Java.perform(function() {
        try {
            var System = Java.use('java.lang.System');
            var Process = Java.use('android.os.Process');

            System.exit.implementation = function(code) {
                log("[!] Intercepted System.exit(" + code + ")");
            };

            Process.killProcess.implementation = function(pid) {
                log("[!] Intercepted Process.killProcess for PID: " + pid);
            };
        } catch (e) {
            log("[-] Error hooking anti-tamper: " + e);
        }
    });
});

// --- KEY GENERATION & HASHING ---
setImmediate(function() {
    Java.perform(function () {
        try {
            const SecretKeySpec = Java.use('javax.crypto.spec.SecretKeySpec');
            SecretKeySpec.$init.overload('[B', 'java.lang.String').implementation = function (keyBytes, algorithm) {
                log("\n[!] --- SecretKeySpec Created ---");
                log("Algorithm: " + algorithm);
                log("Key (Hex): " + toHex(keyBytes));
                printStackTrace("Key Origin Trace");
                return this.$init(keyBytes, algorithm);
            };

            const MessageDigest = Java.use('java.security.MessageDigest');
            MessageDigest.digest.overload('[B').implementation = function (input) {
                const result = this.digest(input);
                log("\n[+] --- MessageDigest.digest() ---");
                log("Algorithm: " + this.getAlgorithm());
                log("Input (Hex): " + toHex(input));
                log("Output Hash (Hex): " + toHex(result));
                return result;
            };
        } catch (e) {
            log("[-] Error hooking Key Gen/Hashing: " + e);
        }
    });
});

// --- ENCRYPTION OPERATIONS (CIPHER) ---
setImmediate(function() {
    Java.perform(function () {
        try {
            const Cipher = Java.use('javax.crypto.Cipher');
            var cipherStates = {};

            // 1. Hook init()
            const initOverloads = Cipher.init.overloads;
            initOverloads.forEach(function (overload) {
                overload.implementation = function () {
                    const result = overload.apply(this, arguments);
                    const opmode = arguments[0];
                    const key = arguments[1];
                    const iv = this.getIV();
                    const modeName = (opmode === 1) ? "ENCRYPT" : (opmode === 2) ? "DECRYPT" : opmode;
                    
                    cipherStates[this.hashCode()] = {
                        mode: modeName,
                        algo: this.getAlgorithm(),
                        key: key ? toHex(key.getEncoded()) : "null",
                        iv: (iv && iv.length > 0) ? toHex(iv) : "null"
                    };

                    console.log("\n[+] --- Cipher.init() ---");
                    console.log("State: " + cipherStates[this.hashCode()]);
                    console.log("Mode: " + modeName);
                    console.log("Algorithm: " + this.getAlgorithm());

                    if (key) {
                        console.log("Key (Hex): " + toHex(key.getEncoded()));
                    }
                    if (iv) {
                        console.log("IV/Nonce (Hex): " + toHex(iv));
                    }

                    return result;
                };
            });

            // 2. Hook update() for chunked data
            const updateOverloads = Cipher.update.overloads;
            updateOverloads.forEach(function (overload) {
                overload.implementation = function () {
                    const input = arguments[0];
                    const result = overload.apply(this, arguments);
                    const state = cipherStates[this.hashCode()];
                    
                    if (state) {
                        log("\n[~] --- Cipher.update() CHUNK ---");
                        log("Algorithm : " + state.algo + " (" + state.mode + ")");
                        if (input && input.length > 0) log("Input     : " + toHex(input));
                        if (result && result.length > 0) log("Output    : " + toHex(result));
                    } else {
                        log("Missing state for encryption .update() hook!");
                    }
                    return result;
                };
            });

            // 3. Hook doFinal()
            const doFinalOverloads = Cipher.doFinal.overloads;
            doFinalOverloads.forEach(function (overload) {
                overload.implementation = function () {
                    const input = arguments[0];
                    const result = overload.apply(this, arguments);
                    const state = cipherStates[this.hashCode()];
                    
                    if (state) {
                        log("\n[+] --- SECURE PAYLOAD CAPTURED ---");
                        log("Algorithm : " + state.algo + " (" + state.mode + ")");
                        log("Key (Hex) : " + state.key);
                        log("IV  (Hex) : " + state.iv);
                        // Optional: if input is a primitive array, this works. If ByteBuffer, toHex catches it.
                        if (input) log("Input     : " + toHex(input));
                        if (result) log("Output    : " + toHex(result));
                        log("-----------------------------------");
                    } else {
                        log("Missing state for encryption .doFinal() hook!");
                    }
                    return result;
                };
            });
        } catch (e) {
            log("[-] Error hooking Cipher: " + e);
        }
    });
});

// --- BLUETOOTH I/O ---
setImmediate(function() {
    Java.perform(function () {
        try {
            const BluetoothGatt = Java.use('android.bluetooth.BluetoothGatt');
            const BluetoothGattCharacteristic = Java.use('android.bluetooth.BluetoothGattCharacteristic');

            const writeOverloads = BluetoothGatt.writeCharacteristic.overloads;
            writeOverloads.forEach(function (overload) {
                overload.implementation = function () {
                    const char = arguments[0];
                    let data = (arguments.length >= 2) ? arguments[1] : char.getValue();

                    log("\n[BLE WRITE] UUID: " + char.getUuid());
                    // Safe type check before parsing
                    if (data !== null && typeof data === 'object') {
                        log("Data (Hex): " + toHex(data));
                        printStackTrace("BLE Write Trace");
                    } else {
                        log("BLE write data not safe!");
                    }
                    return overload.apply(this, arguments);
                };
            });

            const setValueOverloads = BluetoothGattCharacteristic.setValue.overloads;
            setValueOverloads.forEach(function (overload) {
                overload.implementation = function () {
                    const uuid = this.getUuid().toString();
                    const value = arguments[0];

                    log("\n[BLE NOTIFY] UUID: " + uuid);
                    if (value !== null && typeof value === 'object') {
                         log("Data (Hex): " + toHex(value));
                    } else {
                        log("BLE notify data not safe!");
                    }
                    return overload.apply(this, arguments);
                };
            });
        } catch (e) {
            log("[-] Error hooking Bluetooth: " + e);
        }
    });
});