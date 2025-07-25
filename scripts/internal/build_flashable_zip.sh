#!/usr/bin/env bash
#
# Copyright (C) 2023 Salvo Giangreco
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

# shellcheck disable=SC2162

set -Eeo pipefail

# [
GET_PROP()
{
    local PROP="$1"
    local FILE="$2"

    if [ ! -f "$FILE" ]; then
        echo "File not found: $FILE"
        exit 1
    fi

    grep "^$PROP=" "$FILE" | cut -d "=" -f2-
}

PRINT_HEADER()
{
    local ONEUI_VERSION
    local MAJOR
    local MINOR
    local PATCH

    ONEUI_VERSION="$(GET_PROP "ro.build.version.oneui" "$WORK_DIR/system/system/build.prop")"
    MAJOR=$(echo "scale=0; $ONEUI_VERSION / 10000" | bc -l)
    MINOR=$(echo "scale=0; $ONEUI_VERSION % 10000 / 100" | bc -l)
    PATCH=$(echo "scale=0; $ONEUI_VERSION % 100" | bc -l)
    if [[ "$PATCH" != "0" ]]; then
        ONEUI_VERSION="$MAJOR.$MINOR.$PATCH"
    else
        ONEUI_VERSION="$MAJOR.$MINOR"
    fi

    echo    'ui_print(" ");'
    echo    'ui_print("****************************************");'
    echo -n 'ui_print("'
    echo -n "ExtremeROM $ROM_CODENAME $ROM_VERSION for $TARGET_NAME"
    echo    '");'
    echo    'ui_print("ROM by ExtremeXT @XDAforums");'
    echo    'ui_print("Build system coded by salvo_giangri @XDAforums");'
    echo    'ui_print("****************************************");'
    echo -n 'ui_print("'
    echo -n "One UI version: $ONEUI_VERSION"
    echo    '");'
    echo -n 'ui_print("'
    echo -n "Source: $(GET_PROP "ro.system.build.fingerprint" "$WORK_DIR/system/system/build.prop")"
    echo    '");'
    echo -n 'ui_print("'
    echo -n "Target: $(GET_PROP "ro.vendor.build.fingerprint" "$WORK_DIR/vendor/build.prop")"
    echo    '");'
    echo    'ui_print("****************************************");'
}

GET_SPARSE_IMG_SIZE()
{
    local FILE_INFO
    local BLOCKS
    local BLOCK_SIZE

    FILE_INFO=$(file -b "$1")
    if [ -z "$FILE_INFO" ] || [[ "$FILE_INFO" != "Android"* ]]; then
        exit 1
    fi

    BLOCKS=$(echo "$FILE_INFO" | grep -o "[[:digit:]]*" | sed "3p;d")
    BLOCK_SIZE=$(echo "$FILE_INFO" | grep -o "[[:digit:]]*" | sed "4p;d")

    echo "$BLOCKS * $BLOCK_SIZE" | bc -l
}

GENERATE_OP_LIST()
{
    local OP_LIST_FILE="$TMP_DIR/dynamic_partitions_op_list"
    local PART_SIZE=0
    local OCCUPIED_SPACE=0
    local HAS_SYSTEM=false
    local HAS_VENDOR=false
    local HAS_PRODUCT=false
    local HAS_SYSTEM_EXT=false
    local HAS_ODM=false
    local HAS_VENDOR_DLKM=false
    local HAS_ODM_DLKM=false
    local HAS_SYSTEM_DLKM=false

    [ -f "$TMP_DIR/system.img" ] && HAS_SYSTEM=true
    [ -f "$TMP_DIR/vendor.img" ] && HAS_VENDOR=true
    [ -f "$TMP_DIR/product.img" ] && HAS_PRODUCT=true
    [ -f "$TMP_DIR/system_ext.img" ] && HAS_SYSTEM_EXT=true
    [ -f "$TMP_DIR/odm.img" ] && HAS_ODM=true
    [ -f "$TMP_DIR/vendor_dlkm.img" ] && HAS_VENDOR_DLKM=true
    [ -f "$TMP_DIR/odm_dlkm.img" ] && HAS_ODM_DLKM=true
    [ -f "$TMP_DIR/system_dlkm.img" ] && HAS_SYSTEM_DLKM=true

    [ -f "$OP_LIST_FILE" ] && rm -f "$OP_LIST_FILE"
    touch "$OP_LIST_FILE"
    {
        echo "# Remove all existing dynamic partitions and groups before applying full OTA"
        echo "remove_all_groups"
        echo "# Add group $TARGET_SUPER_GROUP_NAME with maximum size $TARGET_SUPER_GROUP_SIZE"
        echo "add_group $TARGET_SUPER_GROUP_NAME $TARGET_SUPER_GROUP_SIZE"
        $HAS_SYSTEM && echo "# Add partition system to group $TARGET_SUPER_GROUP_NAME"
        $HAS_SYSTEM && echo "add system $TARGET_SUPER_GROUP_NAME"
        $HAS_VENDOR && echo "# Add partition vendor to group $TARGET_SUPER_GROUP_NAME"
        $HAS_VENDOR && echo "add vendor $TARGET_SUPER_GROUP_NAME"
        $HAS_PRODUCT && echo "# Add partition product to group $TARGET_SUPER_GROUP_NAME"
        $HAS_PRODUCT && echo "add product $TARGET_SUPER_GROUP_NAME"
        $HAS_SYSTEM_EXT && echo "# Add partition system_ext to group $TARGET_SUPER_GROUP_NAME"
        $HAS_SYSTEM_EXT && echo "add system_ext $TARGET_SUPER_GROUP_NAME"
        $HAS_ODM && echo "# Add partition odm to group $TARGET_SUPER_GROUP_NAME"
        $HAS_ODM && echo "add odm $TARGET_SUPER_GROUP_NAME"
        $HAS_VENDOR_DLKM && echo "# Add partition vendor_dlkm to group $TARGET_SUPER_GROUP_NAME"
        $HAS_VENDOR_DLKM && echo "add vendor_dlkm $TARGET_SUPER_GROUP_NAME"
        $HAS_ODM_DLKM && echo "# Add partition odm_dlkm to group $TARGET_SUPER_GROUP_NAME"
        $HAS_ODM_DLKM && echo "add odm_dlkm $TARGET_SUPER_GROUP_NAME"
        $HAS_SYSTEM_DLKM && echo "# Add partition system_dlkm to group $TARGET_SUPER_GROUP_NAME"
        $HAS_SYSTEM_DLKM && echo "add system_dlkm $TARGET_SUPER_GROUP_NAME"
        if $HAS_SYSTEM; then
            PART_SIZE="$(GET_SPARSE_IMG_SIZE "$TMP_DIR/system.img")"
            echo "# Grow partition system from 0 to $PART_SIZE"
            echo "resize system $PART_SIZE"
            OCCUPIED_SPACE=$((OCCUPIED_SPACE + PART_SIZE))
        fi
        if $HAS_VENDOR; then
            PART_SIZE="$(GET_SPARSE_IMG_SIZE "$TMP_DIR/vendor.img")"
            echo "# Grow partition vendor from 0 to $PART_SIZE"
            echo "resize vendor $PART_SIZE"
            OCCUPIED_SPACE=$((OCCUPIED_SPACE + PART_SIZE))
        fi
        if $HAS_PRODUCT; then
            PART_SIZE="$(GET_SPARSE_IMG_SIZE "$TMP_DIR/product.img")"
            echo "# Grow partition product from 0 to $PART_SIZE"
            echo "resize product $PART_SIZE"
            OCCUPIED_SPACE=$((OCCUPIED_SPACE + PART_SIZE))
        fi
        if $HAS_SYSTEM_EXT; then
            PART_SIZE="$(GET_SPARSE_IMG_SIZE "$TMP_DIR/system_ext.img")"
            echo "# Grow partition system_ext from 0 to $PART_SIZE"
            echo "resize system_ext $PART_SIZE"
            OCCUPIED_SPACE=$((OCCUPIED_SPACE + PART_SIZE))
        fi
        if $HAS_ODM; then
            PART_SIZE="$(GET_SPARSE_IMG_SIZE "$TMP_DIR/odm.img")"
            echo "# Grow partition odm from 0 to $PART_SIZE"
            echo "resize odm $PART_SIZE"
            OCCUPIED_SPACE=$((OCCUPIED_SPACE + PART_SIZE))
        fi
        if $HAS_VENDOR_DLKM; then
            PART_SIZE="$(GET_SPARSE_IMG_SIZE "$TMP_DIR/vendor_dlkm.img")"
            echo "# Grow partition vendor_dlkm from 0 to $PART_SIZE"
            echo "resize vendor_dlkm $PART_SIZE"
            OCCUPIED_SPACE=$((OCCUPIED_SPACE + PART_SIZE))
        fi
        if $HAS_ODM_DLKM; then
            PART_SIZE="$(GET_SPARSE_IMG_SIZE "$TMP_DIR/odm_dlkm.img")"
            echo "# Grow partition odm_dlkm from 0 to $PART_SIZE"
            echo "resize odm_dlkm $PART_SIZE"
            OCCUPIED_SPACE=$((OCCUPIED_SPACE + PART_SIZE))
        fi
        if $HAS_SYSTEM_DLKM; then
            PART_SIZE="$(GET_SPARSE_IMG_SIZE "$TMP_DIR/system_dlkm.img")"
            echo "# Grow partition system_dlkm from 0 to $PART_SIZE"
            echo "resize system_dlkm $PART_SIZE"
            OCCUPIED_SPACE=$((OCCUPIED_SPACE + PART_SIZE))
        fi
    } >> "$OP_LIST_FILE"

    if [[ "$OCCUPIED_SPACE" -gt "$TARGET_SUPER_GROUP_SIZE" ]]; then
        echo "OS size ($OCCUPIED_SPACE) is bigger than target group size ($TARGET_SUPER_GROUP_SIZE)."
        exit 1
    fi

    true
}

GENERATE_LPMAKE_OPT()
{
    local OPT
    local HAS_SYSTEM=false
    local HAS_VENDOR=false
    local HAS_PRODUCT=false
    local HAS_SYSTEM_EXT=false
    local HAS_ODM=false
    local HAS_VENDOR_DLKM=false
    local HAS_ODM_DLKM=false
    local HAS_SYSTEM_DLKM=false

    [ -f "$TMP_DIR/system.img" ] && HAS_SYSTEM=true
    [ -f "$TMP_DIR/vendor.img" ] && HAS_VENDOR=true
    [ -f "$TMP_DIR/product.img" ] && HAS_PRODUCT=true
    [ -f "$TMP_DIR/system_ext.img" ] && HAS_SYSTEM_EXT=true
    [ -f "$TMP_DIR/odm.img" ] && HAS_ODM=true
    [ -f "$TMP_DIR/vendor_dlkm.img" ] && HAS_VENDOR_DLKM=true
    [ -f "$TMP_DIR/odm_dlkm.img" ] && HAS_ODM_DLKM=true
    [ -f "$TMP_DIR/system_dlkm.img" ] && HAS_SYSTEM_DLKM=true

    OPT+=" -o $TMP_DIR/unsparse_super_empty.img"
    OPT+=" --device-size $TARGET_SUPER_PARTITION_SIZE"
    OPT+=" --metadata-size 65536 --metadata-slots 2"
    OPT+=" -g $TARGET_SUPER_GROUP_NAME:$TARGET_SUPER_GROUP_SIZE"

    if $HAS_SYSTEM; then
        OPT+=" -p system:readonly:0:$TARGET_SUPER_GROUP_NAME"
    fi
    if $HAS_VENDOR; then
        OPT+=" -p vendor:readonly:0:$TARGET_SUPER_GROUP_NAME"
    fi
    if $HAS_PRODUCT; then
        OPT+=" -p product:readonly:0:$TARGET_SUPER_GROUP_NAME"
    fi
    if $HAS_SYSTEM_EXT; then
        OPT+=" -p system_ext:readonly:0:$TARGET_SUPER_GROUP_NAME"
    fi
    if $HAS_ODM; then
        OPT+=" -p odm:readonly:0:$TARGET_SUPER_GROUP_NAME"
    fi
    if $HAS_VENDOR_DLKM; then
        OPT+=" -p vendor_dlkm:readonly:0:$TARGET_SUPER_GROUP_NAME"
    fi
    if $HAS_ODM_DLKM; then
        OPT+=" -p odm_dlkm:readonly:0:$TARGET_SUPER_GROUP_NAME"
    fi
    if $HAS_SYSTEM_DLKM; then
        OPT+=" -p system_dlkm:readonly:0:$TARGET_SUPER_GROUP_NAME"
    fi

    echo "$OPT"
}

GENERATE_UPDATER_SCRIPT()
{
    local BROTLI_EXTENSION
    [ "$NO_COMPRESSION" = "false" ] && BROTLI_EXTENSION=".br"
    local SCRIPT_FILE="$TMP_DIR/META-INF/com/google/android/updater-script"
    local PARTITION_COUNT=0
    local HAS_UP_PARAM=false
    local HAS_BOOT=false
    local HAS_DTB=false
    local HAS_DTBO=false
    local HAS_INIT_BOOT=false
    local HAS_VENDOR_BOOT=false
    local HAS_SUPER_EMPTY=false
    local HAS_SYSTEM=false
    local HAS_VENDOR=false
    local HAS_PRODUCT=false
    local HAS_SYSTEM_EXT=false
    local HAS_ODM=false
    local HAS_VENDOR_DLKM=false
    local HAS_ODM_DLKM=false
    local HAS_SYSTEM_DLKM=false
    local HAS_PRISM=false
    local HAS_OPTICS=false
    local HAS_POST_INSTALL=false

    [ -f "$TMP_DIR/up_param.bin" ] && HAS_UP_PARAM=true
    [ -f "$TMP_DIR/boot.img" ] && HAS_BOOT=true
    [ -f "$TMP_DIR/dtb.img" ] && HAS_DTB=true
    [ -f "$TMP_DIR/dtbo.img" ] && HAS_DTBO=true
    [ -f "$TMP_DIR/init_boot.img" ] && HAS_INIT_BOOT=true
    [ -f "$TMP_DIR/vendor_boot.img" ] && HAS_VENDOR_BOOT=true
    [ -f "$TMP_DIR/unsparse_super_empty.img" ] && HAS_SUPER_EMPTY=true
    [ -f "$TMP_DIR/system.new.dat${BROTLI_EXTENSION}" ] && HAS_SYSTEM=true
    [ -f "$TMP_DIR/vendor.new.dat${BROTLI_EXTENSION}" ] && HAS_VENDOR=true && PARTITION_COUNT=$((PARTITION_COUNT + 1))
    [ -f "$TMP_DIR/product.new.dat${BROTLI_EXTENSION}" ] && HAS_PRODUCT=true && PARTITION_COUNT=$((PARTITION_COUNT + 1))
    [ -f "$TMP_DIR/system_ext.new.dat${BROTLI_EXTENSION}" ] && HAS_SYSTEM_EXT=true && PARTITION_COUNT=$((PARTITION_COUNT + 1))
    [ -f "$TMP_DIR/odm.new.dat${BROTLI_EXTENSION}" ] && HAS_ODM=true && PARTITION_COUNT=$((PARTITION_COUNT + 1))
    [ -f "$TMP_DIR/vendor_dlkm.new.dat${BROTLI_EXTENSION}" ] && HAS_VENDOR_DLKM=true && PARTITION_COUNT=$((PARTITION_COUNT + 1))
    [ -f "$TMP_DIR/odm_dlkm.new.dat${BROTLI_EXTENSION}" ] && HAS_ODM_DLKM=true && PARTITION_COUNT=$((PARTITION_COUNT + 1))
    [ -f "$TMP_DIR/system_dlkm.new.dat${BROTLI_EXTENSION}" ] && HAS_SYSTEM_DLKM=true && PARTITION_COUNT=$((PARTITION_COUNT + 1))
    [ -f "$TMP_DIR/prism.new.dat${BROTLI_EXTENSION}" ] && HAS_PRISM=true
    [ -f "$TMP_DIR/optics.new.dat${BROTLI_EXTENSION}" ] && HAS_OPTICS=true
    [ -f "$SRC_DIR/target/$TARGET_CODENAME/postinstall.edify" ] && HAS_POST_INSTALL=true

    [ -f "$SCRIPT_FILE" ] && rm -f "$SCRIPT_FILE"
    touch "$SCRIPT_FILE"
    {
        if [ -n "$TARGET_ASSERT_MODEL" ]; then
            IFS=':' read -a TARGET_ASSERT_MODEL <<< "$TARGET_ASSERT_MODEL"
            for i in "${TARGET_ASSERT_MODEL[@]}"
            do
                echo -n 'getprop("ro.boot.em.model") == "'
                echo -n "$i"
                echo -n '" || '
            done
            echo -n 'abort("E3004: This package is for \"'
            echo -n "$TARGET_CODENAME"
            echo    '\" devices; this is a \"" + getprop("ro.product.device") + "\".");'
        else
            echo -n 'getprop("ro.product.device") == "'
            echo -n "$TARGET_CODENAME"
            echo -n '" || abort("E3004: This package is for \"'
            echo -n "$TARGET_CODENAME"
            echo    '\" devices; this is a \"" + getprop("ro.product.device") + "\".");'
        fi

        PRINT_HEADER

        if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
            echo -e "\n# --- Start patching dynamic partitions ---\n\n"
            echo -e "# Update dynamic partition metadata\n"
            echo -n 'assert(update_dynamic_partitions(package_extract_file("dynamic_partitions_op_list")'
            if $HAS_SUPER_EMPTY; then
                echo -n ', package_extract_file("unsparse_super_empty.img")'
            fi
            echo    '));'
        fi
        if $HAS_SYSTEM; then
            echo -e "\n# Patch partition system\n"
            echo    'ui_print("Patching system image unconditionally...");'
            echo -n 'show_progress(0.'
            echo "9 - $PARTITION_COUNT" | bc -l | tr -d "\n"
            echo    '00000, 0);'
            echo -n    'block_image_update('
            if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
                echo -n    'map_partition("system"), '
            else
                echo -n    '"'
                echo -n    "$TARGET_BOOT_DEVICE_PATH"
                echo -n    '/system", '
            fi
            echo -n    'package_extract_file("system.transfer.list"), '
            echo -n    "\"system.new.dat${BROTLI_EXTENSION}\""
            echo       ', "system.patch.dat") ||'
            echo    '  abort("E1001: Failed to update system image.");'
        fi
        if $HAS_VENDOR; then
            echo -e "\n# Patch partition vendor\n"
            echo    'ui_print("Patching vendor image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
                echo -n    'map_partition("vendor"), '
            else
                echo -n    '"'
                echo -n    "$TARGET_BOOT_DEVICE_PATH"
                echo -n    '/vendor", '
            fi
            echo -n    'package_extract_file("vendor.transfer.list"), '
            echo -n    "\"vendor.new.dat${BROTLI_EXTENSION}\""
            echo       ', "vendor.patch.dat") ||'
            echo    '  abort("E2001: Failed to update vendor image.");'
        fi
        if $HAS_PRODUCT; then
            echo -e "\n# Patch partition product\n"
            echo    'ui_print("Patching product image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
                echo -n    'map_partition("product"), '
            else
                echo -n    '"'
                echo -n    "$TARGET_BOOT_DEVICE_PATH"
                echo -n    '/product", '
            fi
            echo -n    'package_extract_file("product.transfer.list"), '
            echo -n    "\"product.new.dat${BROTLI_EXTENSION}\""
            echo       ', "product.patch.dat") ||'
            echo    '  abort("E2001: Failed to update product image.");'
        fi
        if $HAS_SYSTEM_EXT; then
            echo -e "\n# Patch partition system_ext\n"
            echo    'ui_print("Patching system_ext image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
                echo -n    'map_partition("system_ext"), '
            else
                echo -n    '"'
                echo -n    "$TARGET_BOOT_DEVICE_PATH"
                echo -n    '/system_ext", '
            fi
            echo -n    'package_extract_file("system_ext.transfer.list"), '
            echo -n    "\"system_ext.new.dat${BROTLI_EXTENSION}\""
            echo       ', "system_ext.patch.dat") ||'
            echo    '  abort("E2001: Failed to update system_ext image.");'
        fi
        if $HAS_ODM; then
            echo -e "\n# Patch partition odm\n"
            echo    'ui_print("Patching odm image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
                echo -n    'map_partition("odm"), '
            else
                echo -n    '"'
                echo -n    "$TARGET_BOOT_DEVICE_PATH"
                echo -n    '/odm", '
            fi
            echo -n    'package_extract_file("odm.transfer.list"), '
            echo -n    "\"odm.new.dat${BROTLI_EXTENSION}\""
            echo       ', "odm.patch.dat") ||'
            echo    '  abort("E2001: Failed to update odm image.");'
        fi
        if $HAS_VENDOR_DLKM; then
            echo -e "\n# Patch partition vendor_dlkm\n"
            echo    'ui_print("Patching vendor_dlkm image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
                echo -n    'map_partition("vendor_dlkm"), '
            else
                echo -n    '"'
                echo -n    "$TARGET_BOOT_DEVICE_PATH"
                echo -n    '/vendor_dlkm", '
            fi
            echo -n    'package_extract_file("vendor_dlkm.transfer.list"), '
            echo -n    "\"vendor_dlkm.new.dat${BROTLI_EXTENSION}\""
            echo       ', "vendor_dlkm.patch.dat") ||'
            echo    '  abort("E2001: Failed to update vendor_dlkm image.");'
        fi
        if $HAS_ODM_DLKM; then
            echo -e "\n# Patch partition odm_dlkm\n"
            echo    'ui_print("Patching odm_dlkm image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
                echo -n    'map_partition("odm_dlkm"), '
            else
                echo -n    '"'
                echo -n    "$TARGET_BOOT_DEVICE_PATH"
                echo -n    '/odm_dlkm", '
            fi
            echo -n    'package_extract_file("odm_dlkm.transfer.list"), '
            echo -n    "\"odm_dlkm.new.dat${BROTLI_EXTENSION}\""
            echo       ', "odm_dlkm.patch.dat") ||'
            echo    '  abort("E2001: Failed to update odm_dlkm image.");'
        fi
        if $HAS_SYSTEM_DLKM; then
            echo -e "\n# Patch partition system_dlkm\n"
            echo    'ui_print("Patching system_dlkm image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
                echo -n    'map_partition("system_dlkm"), '
            else
                echo -n    '"'
                echo -n    "$TARGET_BOOT_DEVICE_PATH"
                echo -n    '/system_dlkm", '
            fi
            echo -n    'package_extract_file("system_dlkm.transfer.list"), '
            echo -n    "\"system_dlkm.new.dat${BROTLI_EXTENSION}\""
            echo       ', "system_dlkm.patch.dat") ||'
            echo    '  abort("E2001: Failed to update system_dlkm image.");'
        fi
        if $HAS_PRISM; then
            echo -e "\n# Patch partition prism\n"
            echo    'ui_print("Patching prism image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            echo -n    '"'
            echo -n    "$TARGET_BOOT_DEVICE_PATH"
            echo -n    '/prism", '
            echo -n    'package_extract_file("prism.transfer.list"), '
            echo -n    "\"prism.new.dat${BROTLI_EXTENSION}\""
            echo       ', "prism.patch.dat") ||'
            echo    '  abort("E2001: Failed to update prism image.");'
        fi
        if $HAS_OPTICS; then
            echo -e "\n# Patch partition optics\n"
            echo    'ui_print("Patching optics image unconditionally...");'
            echo    'show_progress(0.100000, 0);'
            echo -n    'block_image_update('
            echo -n    '"'
            echo -n    "$TARGET_BOOT_DEVICE_PATH"
            echo -n    '/optics", '
            echo -n    'package_extract_file("optics.transfer.list"), '
            echo -n    "\"optics.new.dat${BROTLI_EXTENSION}\""
            echo       ', "optics.patch.dat") ||'
            echo    '  abort("E2001: Failed to update optics image.");'
        fi
        if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
            echo -e "\n# --- End patching dynamic partitions ---\n"
        else
            echo -e "\n"
        fi
        if $HAS_DTB; then
            echo    'ui_print("Full Patching dtb.img img...");'
            echo -n 'package_extract_file("dtb.img", "'
            echo -n "$TARGET_BOOT_DEVICE_PATH"
            echo    '/dtb");'
        fi
        if $HAS_DTBO; then
            echo    'ui_print("Full Patching dtbo.img img...");'
            echo -n 'package_extract_file("dtbo.img", "'
            echo -n "$TARGET_BOOT_DEVICE_PATH"
            echo    '/dtbo");'
        fi
        if $HAS_INIT_BOOT; then
            echo    'ui_print("Full Patching init_boot.img img...");'
            echo -n 'package_extract_file("init_boot.img", "'
            echo -n "$TARGET_BOOT_DEVICE_PATH"
            echo    '/init_boot");'
        fi
        if $HAS_VENDOR_BOOT; then
            echo    'ui_print("Full Patching vendor_boot.img img...");'
            echo -n 'package_extract_file("vendor_boot.img", "'
            echo -n "$TARGET_BOOT_DEVICE_PATH"
            echo    '/vendor_boot");'
        fi
        if $HAS_BOOT; then
            echo    'ui_print("Installing boot image...");'
            echo -n 'package_extract_file("boot.img", "'
            echo -n "$TARGET_BOOT_DEVICE_PATH"
            echo    '/boot");'
        fi
        if $HAS_UP_PARAM; then
            echo    'ui_print("Installing up_param image...");'
            echo -n 'package_extract_file("up_param.bin", "'
            echo -n "$TARGET_BOOT_DEVICE_PATH"
            echo    '/up_param");'
        fi

        if $HAS_POST_INSTALL; then
            cat "$SRC_DIR/target/$TARGET_CODENAME/postinstall.edify"
        fi

        echo    'set_progress(1.000000);'
        echo    'ui_print("****************************************");'
        echo    'ui_print(" ");'
    } >> "$SCRIPT_FILE"

    true
}

GENERATE_BUILD_INFO()
{
    local BUILD_INFO_FILE="$TMP_DIR/build_info.txt"

    [ -f "$BUILD_INFO_FILE" ] && rm -f "$BUILD_INFO_FILE"
    touch "$BUILD_INFO_FILE"
    {
        echo "device=$TARGET_CODENAME"
        echo "version=$ROM_VERSION"
        echo "timestamp=$ROM_BUILD_TIMESTAMP"
        echo "security_patch_version=$(GET_PROP "ro.build.version.security_patch" "$WORK_DIR/system/system/build.prop")"
    } >> "$BUILD_INFO_FILE"

    true
}

ZIP_FILE_NAME="ExtremeROM_${ROM_CODENAME}_${ROM_VERSION}_$(date +%Y%m%d)_${TARGET_CODENAME}.zip"
# ]

echo "Set up tmp dir"
mkdir -p "$TMP_DIR"
[ -d "$TMP_DIR/META-INF/com/google/android" ] && rm -rf "$TMP_DIR/META-INF/com/google/android"
mkdir -p "$TMP_DIR/META-INF/com/google/android"
cp --preserve=all "$SRC_DIR/prebuilts/bootable/deprecated-ota/updater" "$TMP_DIR/META-INF/com/google/android/update-binary"

while read -r i; do
    PARTITION=$(basename "$i")
    [[ "$PARTITION" == "configs" ]] && continue
    [[ "$PARTITION" == "kernel" ]] && continue
    [ -f "$TMP_DIR/$PARTITION.img" ] && rm -f "$TMP_DIR/$PARTITION.img"
    [ -f "$WORK_DIR/$PARTITION.img" ] && rm -f "$WORK_DIR/$PARTITION.img"

    echo "Building $PARTITION.img"
    if [[ "$PARTITION" == "system" || "$PARTITION" == "prism" || "$PARTITION" == "optics" ]]; then
        FILESYSTEM_TYPE="ext4"
    else
        FILESYSTEM_TYPE="$TARGET_OS_FILE_SYSTEM"
    fi
    bash "$SRC_DIR/scripts/build_fs_image.sh" "$FILESYSTEM_TYPE+sparse" "$WORK_DIR/$PARTITION" \
        "$WORK_DIR/configs/file_context-$PARTITION" "$WORK_DIR/configs/fs_config-$PARTITION" > /dev/null 2>&1
    mv "$WORK_DIR/$PARTITION.img" "$TMP_DIR/$PARTITION.img"
done <<< "$(find "$WORK_DIR" -mindepth 1 -maxdepth 1 -type d)"

if [ "$TARGET_SUPER_PARTITION_SIZE" -ne 0 ]; then
    echo "Building unsparse_super_empty.img"
    [ -f "$TMP_DIR/unsparse_super_empty.img" ] && rm -f "$TMP_DIR/unsparse_super_empty.img"
    CMD="lpmake $(GENERATE_LPMAKE_OPT)"
    $CMD &> /dev/null

    echo "Generating dynamic_partitions_op_list"
    GENERATE_OP_LIST
fi

while read -r i; do
    PARTITION="$(basename "$i" | sed "s/.img//g")"

    [[ "$PARTITION" == "unsparse_super_empty" ]] && continue

    if [ -f "$TMP_DIR/$PARTITION.new.dat" ] || [ -f "$TMP_DIR/$PARTITION.new.dat.br" ]; then
        rm -f "$TMP_DIR/$PARTITION.new.dat" \
            && rm -f "$TMP_DIR/$PARTITION.new.dat.br" \
            && rm -f "$TMP_DIR/$PARTITION.patch.dat" \
            && rm -f "$TMP_DIR/$PARTITION.transfer.list"
    fi

    echo "Converting $PARTITION.img to $PARTITION.new.dat"
    img2sdat -o "$TMP_DIR" "$i" > /dev/null 2>&1 \
        && rm "$i"
    if [ "$NO_COMPRESSION" = "false" ]; then
        echo "Compressing $PARTITION.new.dat"
        brotli --quality=6 --output="$TMP_DIR/$PARTITION.new.dat.br" "$TMP_DIR/$PARTITION.new.dat" \
            && rm "$TMP_DIR/$PARTITION.new.dat"
    fi
done <<< "$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type f -name "*.img")"

while read -r i; do
    IMG="$(basename "$i")"
    echo "Copying $IMG"
    [ -f "$TMP_DIR/$IMG" ] && rm -f "$TMP_DIR/$IMG"
    cp -a --preserve=all "$i" "$TMP_DIR/$IMG"
done <<< "$(find "$WORK_DIR/kernel" -mindepth 1 -maxdepth 1 -type f -name "*.img")"

if [ -f "$WORK_DIR/up_param.bin" ]; then
    echo "Copying up_param.bin"
    cp -a "$WORK_DIR/up_param.bin" "$TMP_DIR/up_param.bin"
fi

echo "Generating updater-script"
GENERATE_UPDATER_SCRIPT

echo "Generate build_info.txt"
GENERATE_BUILD_INFO

echo "Creating zip"
[ -f "$OUT_DIR/$ZIP_FILE_NAME" ] && rm -f "$OUT_DIR/$ZIP_FILE_NAME"
cd "$TMP_DIR"
if [ "$NO_COMPRESSION" = "false" ]; then
    zip -rq ../$ZIP_FILE_NAME ./*
else
    zip -rq0 --store ../$ZIP_FILE_NAME ./*
fi
cd - &> /dev/null

echo "Deleting tmp dir"
rm -rf "$TMP_DIR"

exit 0
