/*
 * Script name   : frida.js
 * Description   : Frida script for preventing exit and extracting shared preferences
 * Author        : Harvey Lelliott (@flip-dots)
 * Date          : 16/07/26
 * 
 * License       : MIT
 * Revision      : 1.1.0
 *
 * This script is based off https://codeshare.frida.re/@ninjadiary/frinja---sharedpreferences/
 * but with additional code to prevent the anti-tamper mechanism from killing the app.
*/

// Log any reads/writes to shared preferences
// From: https://codeshare.frida.re/@ninjadiary/frinja---sharedpreferences/
setImmediate(function() {
	Java.perform(function() {
		var contextWrapper = Java.use("android.content.ContextWrapper");
		contextWrapper.getSharedPreferences.overload('java.lang.String', 'int').implementation = function(var0, var1) {
			console.log("[*] getSharedPreferences called with name: " + var0 + " and mode: " + var1 + "\n");
			var sharedPreferences = this.getSharedPreferences(var0, var1);
			return sharedPreferences;
		};

		var sharedPreferencesEditor = Java.use("android.app.SharedPreferencesImpl$EditorImpl");
		sharedPreferencesEditor.putString.overload('java.lang.String', 'java.lang.String').implementation = function(var0, var1) {
			console.log("[*] Added a new String value to SharedPreferences with key: " + var0 + " and value " + var1 + "\n");
			var editor = this.putString(var0, var1);
			return editor;
		}

		sharedPreferencesEditor.putBoolean.overload('java.lang.String', 'boolean').implementation = function(var0, var1) {
			console.log("[*] Added a new boolean value to SharedPreferences with key: " + var0 + " and value " + var1 + "\n");
			var editor = this.putBoolean(var0, var1);
			return editor;
		}

		sharedPreferencesEditor.putFloat.overload('java.lang.String', 'float').implementation = function(var0, var1) {
			console.log("[*] Added a new float value to SharedPreferences with key: " + var0 + " and value " + var1 + "\n");
			var editor = this.putFloat(var0, var1);
			return editor;
		}

		sharedPreferencesEditor.putInt.overload('java.lang.String', 'int').implementation = function(var0, var1) {
			console.log("[*] [*] Added a new int value to SharedPreferences with key: " + var0 + " and value " + var1 + "\n");
			var editor = this.putInt(var0, var1);
			return editor;
		}

		sharedPreferencesEditor.putLong.overload('java.lang.String', 'long').implementation = function(var0, var1) {
			console.log("[*] Added a new long value to SharedPreferences with key: " + var0 + " and value " + var1 + "\n");
			var editor = this.putLong(var0, var1);
			return editor;
		}

		sharedPreferencesEditor.putStringSet.overload('java.lang.String', 'java.util.Set').implementation = function(var0, var1) {
			console.log("[*] Added a new string set to SharedPreferences with key: " + var0 + " and value " + var1 + "\n");
			var editor = this.putStringSet(var0, var1);
			return editor;
		}

		var sharedPreferences = Java.use("android.app.SharedPreferencesImpl");
		sharedPreferences.getString.overload('java.lang.String', 'java.lang.String').implementation = function(var0, var1) {
			console.log("[*] Getting string value from SharedPreferences with key: " + var0 + " and value " + var1 + "\n");
			var stringVal = this.getString(var0, var1);
			return stringVal;
		}
	});
});

// Log any encryption operations
Java.perform(function () {
    const Cipher = Java.use('javax.crypto.Cipher');

    function toHex(byteArray) {
        if (!byteArray) return "null";
        var result = "";
        for (var i = 0; i < byteArray.length; i++) {
            result += ('0' + (byteArray[i] & 0xFF).toString(16)).slice(-2);
        }
        return result;
    }

    // Hook init() to capture Key, IV, Nonce, and Mode
    const initOverloads = Cipher.init.overloads;
    initOverloads.forEach(function (overload) {
        overload.implementation = function () {
            const opmode = arguments[0];
            const key = arguments[1];
            const iv = this.getIV();
            const modeName = (opmode === 1) ? "ENCRYPT" : (opmode === 2) ? "DECRYPT" : opmode;

            console.log("\n[+] --- Cipher.init() ---");
            console.log("Mode: " + modeName);
            console.log("Algorithm: " + this.getAlgorithm());

            if (key) {
                console.log("Key (Hex): " + toHex(key.getEncoded()));
            }
            if (iv) {
                console.log("IV/Nonce (Hex): " + toHex(iv));
            }
            return overload.apply(this, arguments);
        };
    });

    // Hook doFinal() to capture input and output of encryption algorithm
    const doFinalOverloads = Cipher.doFinal.overloads;
    doFinalOverloads.forEach(function (overload) {
        overload.implementation = function () {
            const input = arguments[0];
            const result = overload.apply(this, arguments);

            console.log("\n[+] --- Cipher.doFinal() ---");
            if (input && input.length > 0) {
                console.log("Input (Hex): " + toHex(input));
            }
            if (result && result.length > 0) {
                console.log("Output (Hex): " + toHex(result));
            }
            return result;
        };
    });
});

// Log any Bluetooth I/O
Java.perform(function () {
    const BluetoothGatt = Java.use('android.bluetooth.BluetoothGatt');
    const BluetoothGattCharacteristic = Java.use('android.bluetooth.BluetoothGattCharacteristic');

    function toHex(byteArray) {
        if (!byteArray) return "null";
        var result = "";
        for (var i = 0; i < byteArray.length; i++) {
            result += ('0' + (byteArray[i] & 0xFF).toString(16)).slice(-2);
        }
        return result;
    }

    // Hook BluetoothGatt.writeCharacteristic (Phone -> Device)
    const writeOverloads = BluetoothGatt.writeCharacteristic.overloads;
    writeOverloads.forEach(function (overload) {
        overload.implementation = function () {
            const char = arguments[0];
            let data = (arguments.length >= 2) ? arguments[1] : char.getValue();

            console.log("\n[BLE WRITE] UUID: " + char.getUuid());
            console.log("Data (Hex): " + toHex(data));
            return overload.apply(this, arguments);
        };
    });

    // Hook BluetoothGattCharacteristic.setValue (Device -> Phone)
    const setValueOverloads = BluetoothGattCharacteristic.setValue.overloads;
    setValueOverloads.forEach(function (overload) {
        overload.implementation = function () {
            const uuid = this.getUuid().toString();
            const value = arguments[0];

            console.log("\n[BLE NOTIFY] UUID: " + uuid);
            console.log("Data (Hex): " + toHex(value))
            return overload.apply(this, arguments);
        };
    });
});


/********************** 
 *                    *
 * Anti-Tamper Bypass *
 *                    *
 **********************/


// Prevent anti-tamper mechanism from killing the app in Java
setImmediate(function() {
    Java.perform(function() {
        console.log("Tampering with anti-tamper protection using Java API...");
    
        var System = Java.use('java.lang.System');
        var Process = Java.use('android.os.Process');

        // Stop System.exit()
        System.exit.implementation = function(code) {
            console.log("[!] Intercepted exit (" + code + ")");
        };

        // Stop Process.killProcess()
        Process.killProcess.implementation = function(pid) {
            console.log("[!] Intercepted killProcess for PID: " + pid);
        };
    });
});


// Prevent anti-tamper mechanism from killing the app in C
function blockNativeExit() {
    console.log("Tampering with anti-tamper protection using C API...");

    let usleepAddr = null;
    try {
        usleepAddr = Module.findGlobalExportByName("usleep") || Module.findExportByName("usleep");
    } catch (e) {
        console.log("[-] Could not find usleep globally: " + e.message);
    }

    let nativeUsleep = null;
    if (usleepAddr) {
        nativeUsleep = new NativeFunction(usleepAddr, 'int', ['uint32']);
    }

    // Standard libc functions used by packers to terminate processes
    const exitSymbols = ["exit", "_exit", "abort", "kill", "pthread_exit"];

    exitSymbols.forEach(function (symbol) {
        let address = null;
        try {
            // Find global exports using Frida 17 APIs
            address = Module.findGlobalExportByName(symbol) || Module.findExportByName(symbol);
        } catch (e) {
            // Ignore search errors
        }

        if (address) {
            try {
                Interceptor.attach(address, {
                    onEnter: function (args) {
                        console.log("[!] Native anti-debug triggered " + symbol + "(). Freezing thread to prevent crash...");
                        
                        // Infinite loop using the native OS sleep to halt the calling thread
                        while (true) {
                            if (nativeUsleep) {
                                nativeUsleep(100000); // Sleep for 100ms per iteration safely
                            }
                        }
                    }
                });
                console.log("[+] Hooked native function: " + symbol);
            } catch (e) {
                console.log("[-] Failed to hook: " + symbol + " (" + e.message + ")");
            }
        }
    });
}

blockNativeExit();
