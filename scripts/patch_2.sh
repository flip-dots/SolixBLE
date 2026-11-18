#!/bin/bash
#
# Script name   : patch_2.sh
# Description   : Script for injecting Frida gadget into Anker Android app
# Author        : Harvey Lelliott (@flip-dots)
# Date          : 16/07/26
# Usage         : ./patch_2.sh [ADB device (e.g 192.168.1.1:1234)]
# 
# License       : MIT
# Revision      : 1.0.0
#
set -euxo pipefail


#############
# Constants #
#############

FRIDA_VERSION="17.8.3"

UBER_APK_SIGNER_VERSION="1.3.0"


##################################
# Environment and arg validation #
##################################
echo "Checking environment/tools..."

# Validate arguments
if [ $# -lt 1 ]; then
  echo "Missing device argument (e.g 192.168.1.1:1234)!"
  exit 2
fi

# The device for use with ADB
DEVICE=$1

# Check tools
command -v wget >/dev/null 2>&1 || { echo >&2 "wget is required!"; exit 1; }
command -v adb >/dev/null 2>&1 || { echo >&2 "adb is required!"; exit 1; }
command -v apktool >/dev/null 2>&1 || { echo >&2 "apktool is required!"; exit 1; }
command -v java >/dev/null 2>&1 || { echo >&2 "java is required!"; exit 1; }
command -v frida >/dev/null 2>&1 || { echo >&2 "frida is required!"; exit 1; }


################
# Folder setup #
################
echo "Setting up folders..."

# The current folder
WORKING_FOLDER=$(pwd)

# Folder to put all data in
DATA_FOLDER="${WORKING_FOLDER}/data"
mkdir -p $DATA_FOLDER

# Folder to put source APK inside
APK_SOURCE_FOLDER="${DATA_FOLDER}/source_apks"
mkdir -p $APK_SOURCE_FOLDER

# Folder to put the main decompiled APK inside
APK_MAIN_DECOMPILED_FOLDER="${DATA_FOLDER}/base_apk_decompiled"
mkdir -p $APK_MAIN_DECOMPILED_FOLDER

# Folder to put the flutter decompiled APK inside
APK_FLUTTER_DECOMPILED_FOLDER="${DATA_FOLDER}/flutter_apk_decompiled"
mkdir -p $APK_FLUTTER_DECOMPILED_FOLDER

# Folder to put patched APKs inside
APK_PATCHED_FOLDER="${DATA_FOLDER}/patched"
mkdir -p $APK_PATCHED_FOLDER

# Folder to put signed APKs inside
APK_SIGNED_FOLDER="${DATA_FOLDER}/signed"
mkdir -p $APK_SIGNED_FOLDER

# Folder to put tools in
TOOLS_FOLDER="${WORKING_FOLDER}/tools"
mkdir -p $TOOLS_FOLDER

# Folder to put Frida gadgets in
FRIDA_FOLDER="${TOOLS_FOLDER}/frida"
mkdir -p $FRIDA_FOLDER



#######################
# Download deps/tools #
#######################
echo "Downloading dependencies/tools"

cd $FRIDA_FOLDER && wget "https://github.com/zer0def/undetected-frida/releases/download/${FRIDA_VERSION}/undetected-frida-gadget-${FRIDA_VERSION}-android-arm.so.xz"
cd $FRIDA_FOLDER && wget "https://github.com/zer0def/undetected-frida/releases/download/${FRIDA_VERSION}/undetected-frida-gadget-${FRIDA_VERSION}-android-arm64.so.xz"
cd $FRIDA_FOLDER && unxz -f "undetected-frida-gadget-${FRIDA_VERSION}-android-arm.so.xz"
cd $FRIDA_FOLDER && unxz -f "undetected-frida-gadget-${FRIDA_VERSION}-android-arm64.so.xz"

cd $TOOLS_FOLDER && wget "https://github.com/patrickfav/uber-apk-signer/releases/download/v${UBER_APK_SIGNER_VERSION}/uber-apk-signer-${UBER_APK_SIGNER_VERSION}.jar"


########################
# Pull and extract APK #
########################

# Pull Anker APKs from Phone
echo "Extracting original APKs from phone..."
adb -s $DEVICE shell pm path com.anker.charging | sed 's/^package://' | tr -d '\r' | xargs -I {} adb -s $DEVICE pull {} $APK_SOURCE_FOLDER


################
# Inject Frida #
################
echo "Injecting Frida gadget into flutter APK..."

# Extract Flutter library from Flutter APK
mkdir -p "${APK_FLUTTER_DECOMPILED_FOLDER}/lib/arm64-v8a"
unzip -p "${APK_SOURCE_FOLDER}/split_config.arm64_v8a.apk" "lib/arm64-v8a/libflutter.so" > "${APK_FLUTTER_DECOMPILED_FOLDER}/lib/arm64-v8a/libflutter.so"

# Use LIEF to inject the Frida gadget as a dependency of Flutter
python3 -c "
import lief
import sys

target_path = '${APK_FLUTTER_DECOMPILED_FOLDER}/lib/arm64-v8a/libflutter.so'

try:
    # Parse the ELF binary
    binary = lief.parse(target_path)

    # Inject the dependency
    binary.add_library('libnative-utils.so')
    binary.write(target_path)
    print(f'Successfully injected Frida into Flutter')
except Exception as e:
    print(f'Failed to inject Frida into Flutter: {e}')
    sys.exit(1)
"

# Copy Frida gadget binaries into Flutter APK
cp "${FRIDA_FOLDER}/undetected-frida-gadget-${FRIDA_VERSION}-android-arm64.so" "${APK_FLUTTER_DECOMPILED_FOLDER}/lib/arm64-v8a/libnative-utils.so"
cp "${WORKING_FOLDER}/frida_config.json" "${APK_FLUTTER_DECOMPILED_FOLDER}/lib/arm64-v8a/libnative-utils.config.so"


# Decompile the main APK
echo "Decompiling main APK..."
apktool d "${APK_SOURCE_FOLDER}/base.apk" -o $APK_MAIN_DECOMPILED_FOLDER -f

# Modify manifest of main APK to enable Frida loading
sed -i '' '/<application/,/>/ s/android:allowBackup="false"/android:allowBackup="true"/' "${APK_MAIN_DECOMPILED_FOLDER}/AndroidManifest.xml"
sed -i '' '/<application/,/>/ s/android:extractNativeLibs="false"/android:extractNativeLibs="true" android:debuggable="true"/' "${APK_MAIN_DECOMPILED_FOLDER}/AndroidManifest.xml"



##########################
# Re-package and re-sign #
##########################
echo "Re-packaging and re-signing APKs..."

# Re-package APKs
apktool b -o "${APK_PATCHED_FOLDER}/base.apk" ${APK_MAIN_DECOMPILED_FOLDER}

cp "${APK_SOURCE_FOLDER}/split_config.arm64_v8a.apk" "${APK_PATCHED_FOLDER}/split_config.arm64_v8a.apk"
cd "${APK_FLUTTER_DECOMPILED_FOLDER}" && zip -ur "${APK_PATCHED_FOLDER}/split_config.arm64_v8a.apk" lib/

# Re-sign APKs
java -jar "${TOOLS_FOLDER}/uber-apk-signer-${UBER_APK_SIGNER_VERSION}.jar" -o $APK_SIGNED_FOLDER --allowResign --apks \
   "${APK_PATCHED_FOLDER}/base.apk" \
   "${APK_PATCHED_FOLDER}/split_config.arm64_v8a.apk" \
   "${APK_SOURCE_FOLDER}/split_config.en.apk" \
   "${APK_SOURCE_FOLDER}/split_config.xxhdpi.apk" \
   "${APK_SOURCE_FOLDER}/split_flutter_assets_pack.apk"

# Uninstall existing Anker app
adb -s $DEVICE uninstall com.anker.charging

# Install patched APKs
adb -s $DEVICE install-multiple \
    "${APK_SIGNED_FOLDER}/base-aligned-debugSigned.apk" \
    "${APK_SIGNED_FOLDER}/split_config.arm64_v8a-aligned-debugSigned.apk" \
    "${APK_SIGNED_FOLDER}/split_config.en-aligned-debugSigned.apk" \
    "${APK_SIGNED_FOLDER}/split_config.xxhdpi-aligned-debugSigned.apk" \
    "${APK_SIGNED_FOLDER}/split_flutter_assets_pack-aligned-debugSigned.apk"
