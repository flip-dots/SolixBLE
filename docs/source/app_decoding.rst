App decoding
============

In order to fix protocol incompatibilities and/or add support for controlling a device, it may
be necessary to intercept the connection between the Anker app and the device. This allows for
analysis of what commands sent by the app do what, and how different devices negotiate.
How to perform this is covered in this section.


Requirements
------------

Device requirements:

- Android device with developer mode enabled.
- Anker app installed on the device.

Software requirements:

- `bash`
- `wget`
- `adb`
- `apktool`
- `java`
- `frida`


Patching
--------

In order to capture the messages sent between the phone and the device the app must be patched
to include `Frida <https://frida.re/>`_. Frida is a dynamic instrumentation toolkit which allows
for us to `hook <https://en.wikipedia.org/wiki/Hooking>`_ functions, this is necessary to dump 
`shared preferences <https://developer.android.com/training/data-storage/shared-preferences>`_, get logs of all packets sent and received, as well as providing us a view of
the `encryption functions <https://developer.android.com/reference/javax/crypto/Cipher>`_. Patching can be done `manually <https://koz.io/using-frida-on-android-without-root/>`_, 
using tools by `others <https://github.com/kiks7/frida-non-root/tree/master>`_ or the `patch.sh` 
script inside the scripts folder of the project repository.

.. note::
    If your device is rooted you can use `frida-server <https://deepwiki.com/frida/frida/3.4-frida-server-and-gadget>`_ instead of this approach.


patch.sh
^^^^^^^^

This script is provided to automate the process of patching the Anker app. It takes one 
argument which is the ID of the Android device with the Anker app installed
(e.g `192.168.1.1:1234`, `ABCDEF`, etc), and then automatically copies the Anker app from the
device, patches it, and installs the new patched version. It is designed to be called from
the scripts directory.

.. note::
    If you do not know the devices ID you can use `adb devices -l` to discover it.


This script performs the following actions:

1. Downloads (some) tools and dependencies needed to patch the app.
2. Downloads the installed Anker app from the connected Android device.
3. De-compiles/unpacks the Anker app.
4. Injects `Frida gadget <https://frida.re/docs/gadget/>`_ into the Anker apps files.
5. Modifies `AndroidManifest.xml` to support using Frida gadget.
6. Re-packages the APK.
7. Re-signs the APK.
8. Uninstalls the old Anker app.
9. Installs the patched Anker app.

Example usage:

.. code-block:: bash

    ./patch.sh 192.168.0.1:1234


.. note::
    The patched Anker app will not be usable for regular usage, it will only work 
    when Frida is being run to actively patch the app.


Using modified app
------------------

The modified app can be used with the Frida script to capture all Bluetooth 
packets, the encryption keys, shared preferences, and plain/cipher texts. 

The Anker app features a fairly robust anti-tamper mechanism which is non-trivial
to evade. Instead the Frida script disables the anti-tamper mechanisms ability 
to kill the app, this means you must execute the Frida script within at most
a second of opening the app.

To manually capture the logs follow these steps:

1. Port forward the port used by Frida gadget: 
   `adb -s <your device> forward tcp:49152 tcp:49152`.
2. Open the Anker app on the device.
3. Immediately execute: 
   `frida -H 127.0.0.1:49152 -n Gadget -l scripts/frida.js`.
4. The app will crash but Frida should remain open. 
5. Re-open the app on the device.
6. Perform the actions required to get the packets needed for analysis (add device, send commands, etc).

.. note::
    This process is incredibly time sensitive, it may take multiple attempts to get it right.


run.sh
^^^^^^

This script is provided to automate the steps required to use the modified app
and in addition writes the logs to a file as well as the console. This is 
the recommend approach.

.. note::
    The app must not be running when you start the script.

This script performs the following actions:

1. Starts the app.
2. Executes the frida.js script.
3. Waits 5 seconds and re-opens the app.

When the app has re-opened you should then perform the actions you wish to observe
the result of. If you wish to observe a negotiation you should connect 
to a new device in the Anker app, or if you wish to observe what bytes are
sent when you turn a switch on/off you should turn that switch on/off in the 
app and observe the log output. These log outputs can then be used to add 
equivalent functionality to this library, see :ref:`new device control <new_device_control>`
for more information.

Example usage:

.. code-block:: bash

    ./run.sh 192.168.0.1:1234

.. note::
    The script is more reliable than executing the steps by hand but still fails, it may be necessary to try several times.


Example captures
----------------------

Below are example outputs of the patched app with the Frida script.

.. code-block:: bash
   :linenos:
   :caption: Example log output including encryption, writing BLE data, and shared preferences.

   [+] --- Cipher.init() ---
   Mode: ENCRYPT
   Algorithm: AES/GCM/NoPadding
   Key (Hex): b8ff7422955d4eb6d554a2c470280559

   [+] --- Cipher.doFinal() ---
   Input (Hex): a104f178c169
   Output (Hex): 0a82ceaa27534ee0681742badc14e61ea9bd1c70776c
   [*] Added a new boolean value to SharedPreferences with key: flutter.isBleConnected and value true


   [BLE WRITE] UUID: 8c850002-0302-41c5-b46e-cf057c562025
   Data (Hex): ff09200003000140010a82ceaa27534ee0681742badc14e61ea9bd1c70776c77


.. code-block:: bash
   :linenos:
   :caption: Example log output including receiving BLE data, decryption, and shared preferences.

   [BLE NOTIFY] UUID: 8c850003-0302-41c5-b46e-cf057c562025
   Data (Hex): ff0929000301114a0ab40833040922fad9c2ec9f4683c68fc6ce4f7faa3c62733f1b361f495bc5085f
   [*] Getting string value from SharedPreferences with key: ecdh-keye8ad18f61bbd3fbd52d5ed12d14d3b9c and value 

   [+] --- Cipher.init() ---
   Mode: DECRYPT
   Algorithm: AES/GCM/NoPadding
   Key (Hex): e0ed5b45a01466efada647a212aa79f0
   IV/Nonce (Hex): 471f692c44b6ab6319cb3a63

   [+] --- Cipher.doFinal() ---
   Input (Hex): b40833040922fad9c2ec9f4683c68fc6ce4f7faa3c62733f1b361f495bc508
   Output (Hex): 00a10131a2020100fe050300000000
   [*] Added a new String value to SharedPreferences with key: flutter.deviceCustomProtocolASHDK7U1F51501771 and value {"version":"v1.1.1","port_list":[{"title":"C1","ports":["C1"],"protocols":[{"range":"C1","subTitle":"C1","list":[{"name":"UFCS","status":1},{"name":"SCP","status":1},{"name":"PD 12V","status":0},{"name":"5-11V PPS","status":1},{"name":"5-16V PPS","status":1},{"name":"4.5-21V PPS","status":1}]}],"tlv":[59]},{"title":"C2","ports":["C2"],"protocols":[{"range":"C2","subTitle":"C2","list":[{"name":"UFCS","status":1},{"name":"SCP","status":1},{"name":"PD 12V","status":0},{"name":"5-11V PPS","status":1},{"name":"5-16V PPS","status":1},{"name":"4.5-21V PPS","status":1}]}],"tlv":[59]},{"title":"C3","ports":["C3"],"protocols":[{"range":"C3","subTitle":"C3","list":[{"name":"UFCS","status":1},{"name":"SCP","status":1},{"name":"PD 12V","status":0},{"name":"5-11V PPS","status":1},{"name":"5-16V PPS","status":1},{"name":"4.5-21V PPS","status":1}]}],"tlv":[59]}]}


.. code-block:: bash
   :linenos:
   :caption: Example log output including encryption/decryption, sending/receiving BLE data, key negotiation, and shared preferences.

   [+] --- Cipher.init() ---
   Mode: ENCRYPT
   Algorithm: AES/GCM/NoPadding
   Key (Hex): b8ff7422955d4eb6d554a2c470280559
   IV/Nonce (Hex): 6ba3e3f2f3a60f2971ce5d1f

   [+] --- Cipher.doFinal() ---
   Input (Hex): a104f178c169a30120a4022901a50144a60102
   Output (Hex): 0a82ceaa27538ab3de100ae04aca6791257881fa9bded4360e2e18a10a4f37155e4646

   [BLE WRITE] UUID: 8c850002-0302-41c5-b46e-cf057c562025
   Data (Hex): ff092d0003000140050a82ceaa27538ab3de100ae04aca6791257881fa9bded4360e2e18a10a4f37155e46464e

   [BLE NOTIFY] UUID: 8c850003-0302-41c5-b46e-cf057c562025
   Data (Hex): ff091b000300014805abab709a595a803dd04246b78a927453cf65

   [+] --- Cipher.init() ---
   Mode: DECRYPT
   Algorithm: AES/GCM/NoPadding
   Key (Hex): b8ff7422955d4eb6d554a2c470280559
   IV/Nonce (Hex): 6ba3e3f2f3a60f2971ce5d1f

   [+] --- Cipher.doFinal() ---
   Input (Hex): abab709a595a803dd04246b78a927453cf
   Output (Hex): 00
   [*] getSharedPreferences called with name: com.anker.charging_ifs and mode: 0

   [*] Getting string value from SharedPreferences with key: ecdh_key and value 

   [*] Added a new String value to SharedPreferences with key: ecdh_key and value {"appPrivateKey":"00f94c23e724cab6adf2b8b8767609af78af6423844b0ade6c1380b813b803af5e","appPublicKey":"0478242a84f8a9502b9d183e8c7da30d1630d9c2ca8d05800e79cf17e30745e4761486e35721036a8d21031ddc207807bf906e056d5aec1b1d1b7330d58e8552f9","serverPublicKey":"04c5c00c4f8d1197cc7c3167c52bf7acb054d722f0ef08dcd7e0883236e0d72a3868d9750cb47fa4619248f3d83f0f662671dadc6e2d31c2f41db0161651c7c076"}

   [+] --- Cipher.init() ---
   Mode: ENCRYPT
   Algorithm: AES/GCM/NoPadding
   Key (Hex): b8ff7422955d4eb6d554a2c470280559
   IV/Nonce (Hex): 6ba3e3f2f3a60f2971ce5d1f

   [+] --- Cipher.doFinal() ---
   Input (Hex): a14078242a84f8a9502b9d183e8c7da30d1630d9c2ca8d05800e79cf17e30745e4761486e35721036a8d21031ddc207807bf906e056d5aec1b1d1b7330d58e8552f9
   Output (Hex): 0ac647f6ccbed11bae9f95d175e31b768e6fb309f82e4d8776e1999923b2fc7b34ecd8c19dc1923cd3e1370ab601eb2454eebe3f0df91572b04f8c2fddb802cc5e8ac304fe7f9c34f41794528e1fc69e8417

   [BLE WRITE] UUID: 8c850002-0302-41c5-b46e-cf057c562025
   Data (Hex): ff095c0003000140210ac647f6ccbed11bae9f95d175e31b768e6fb309f82e4d8776e1999923b2fc7b34ecd8c19dc1923cd3e1370ab601eb2454eebe3f0df91572b04f8c2fddb802cc5e8ac304fe7f9c34f41794528e1fc69e84171a


When Java Cipher hooks aren't enough
------------------------------------

The hooks in ``frida.js`` intercept Java-side ``javax.crypto.Cipher``
calls, which is sufficient for devices whose Anker-app integration
performs BLE crypto in Java. Other devices (notably the
:doc:`Solarbank 2 <solarbank2>`) instead perform their per-session BLE
AES inside the **Dart AOT** code in ``libapp.so`` using the
``pointycastle`` library. The Java Cipher hooks never fire for that
traffic, so the session key cannot be recovered through them.

For these devices the session key and IV are installed via Dart calls
such as ``BleInfoHelper::setAesKey(mac, key)`` and ``setAesIV(mac, iv)``
shortly after the ECDH stage completes. Hooking them requires:

1. Extracting the Dart AOT symbol table from ``libapp.so`` to locate the
   target methods. Use `apktool`` for unpacking the APK in
   the first place. Afterwards `blutter <https://github.com/worawit/blutter>`_
   reverses Flutter/Dart AOT snapshots and produces a method table with
   offsets and class-id (cid) information that is then implemented in the
   Frida script.
2. A Frida script that attaches at those offsets via
   ``Module.findBaseAddress("libapp.so").add(<offset>)`` and decodes
   the Dart ``List<int>`` argument according to its cid. These scripts
   will probably only work for a certain app and ABI version. 
   You will need to update the adresses for every app change. The sample 
   SB2 capture script ``scripts/frida_3.js`` in the repository works 
   for Anker App 3.18.0

Scripts
-------

The scripts are provided below for convenience in addition to being in the main repository.


patch.sh
^^^^^^^^

This script automates the patching of the Anker app

.. literalinclude :: ../../scripts/patch.sh
   :language: bash


frida.js
^^^^^^^^

This script neuters the anti-tamper detection of the Anker app and
hooks the shared preferences, encryption, and bluetooth functions to 
log their inputs and outputs.

.. literalinclude :: ../../scripts/frida.js
   :language: javascript


run.sh
^^^^^^

This script executes the modified Anker app and logs the output to a file.

.. literalinclude :: ../../scripts/run.sh
   :language: bash
