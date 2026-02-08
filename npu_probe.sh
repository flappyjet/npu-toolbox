#!/bin/bash

get_vendor_npu() {
    local vendor_devices=("/dev/galcore" "/dev/rknpu")
    for dev in "${vendor_devices[@]}"; do
        if [[ -e "$dev" ]]; then
            echo "$dev"
            break
        fi
    done
}
get_linux_npu() {
    # modern style
    if [[ -d "/sys/class/accel" ]]; then
        for dev in /sys/class/accel/accel*; do
            [[ -e "$dev" ]] || continue
            local drv=$(cat "$dev/device/uevent" | grep "DRIVER=" | cut -d= -f2)
            echo "/dev/${dev##*/}|$drv"
        done
    fi

    # old style
    if [[ -d "/sys/class/drm" ]]; then
        for dev in /sys/class/drm/renderD*; do
            [[ -e "$dev" ]] || continue
            local drv=$(cat "$dev/device/uevent" | grep "DRIVER=" | cut -d= -f2)
            # filter well-known gpu drivers
            [[ "$drv" =~ ^(i915|amdgpu|radeon|nouveau|panfrost|panthor|virtio-gpu)$ ]] && continue
            echo "/dev/dri/${dev##*/}|$drv"
        done
    fi
}
find_lib() {
    local lib_name="$1"
    # env variable
    IFS=':' read -ra paths <<< "$LD_LIBRARY_PATH"
    for dir in "${paths[@]}"; do
        [[ -f "$dir/$lib_name" ]] && { echo "$dir/$lib_name"; return 0; }
    done
    # ld cache
    local ld_cache="$(ldconfig -p 2>/dev/null | grep -E "$lib_name" | awk -F'=>[[:space:]]*' '{print $NF}')"
    while IFS= read -r libpath; do
        [[ -f "$libpath" ]] && { echo "$libpath"; return 0; }
    done <<< $ld_cache

    # linux lib
    libpath="$(find /usr/local/lib /usr/lib -name "$lib_name" 2>/dev/null | head -n 1)"
    [[ -f "$libpath" ]] && { echo "$libpath"; return 0; }

    return 1;
}
(
    echo "# Auto-generated NPU detection record"
    echo "# Generated at: $(date)"

    echo -e "\n[platform]"
    KVER=$(uname -r)
    ARCH=$(uname -m)
    BOARDMODEL=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "unknown")
    SOC=$(tr -d '\0' < /sys/devices/soc0/soc_id 2>/dev/null || echo "unknown")
    echo "model=\"$BOARDMODEL\""
    echo "soc_id=\"$SOC\""
    echo "arch=\"$ARCH\""
    echo "kernel=\"$KVER\""

    # kernel modules
    echo -e "\n[modules]"
    MOD_PATH="/lib/modules/$KVER/kernel/drivers"
    KO_RKNPU="$(find $MOD_PATH -name "rknpu.ko" 2>/dev/null | head -n 1)"
    KO_ETHOS="$(find $MOD_PATH -name "ethos*.ko" 2>/dev/null | head -n 1)"
    KO_GALCORE="$(find $MOD_PATH -name "galcore.ko" 2>/dev/null | head -n 1)"
    KO_ETNAVIV="$(find $MOD_PATH -name "etnaviv.ko" 2>/dev/null | head -n 1)"
    KO_ACCEL="$(find $MOD_PATH -name "rocket.ko" 2>/dev/null | head -n 1)"
    echo "rknpu=\"$KO_RKNPU\""
    echo "ethos=\"$KO_ETHOS\""
    echo "galcore=\"$KO_GALCORE\""
    echo "etanviv=\"$KO_ETNAVIV\""
    echo "rocket=\"$KO_ACCEL\""

    echo -e "\n[devices]"

    # detect NPU devices 
    vendor_node="$(get_vendor_npu)"
    nodes=()
    drivers=()
    while IFS='|' read -r node driver; do
        [ -z "$node" ] && continue
        nodes+=("$node")
        drivers+=("$driver")
    done <<< "$(get_linux_npu)"

    for i in "${!nodes[@]}"; do
        #echo "$i  ${nodes[$i]} # Driver: ${drivers[$i]}"
        if [[ "${drivers[$i]}" =~ ^(etnaviv|rocket)$ ]]; then
            target_idx=$i
            break
        fi
    done

    # print NPU devices
    if [[ -n "$vendor_node" ]]; then
        echo "npu_device=\"$vendor_node\" # Driver: <vendor>"
    elif [[ -n "$target_idx" ]]; then
        echo "npu_device=\"${nodes[$target_idx]}\" # Driver: ${drivers[$i]}"
        if [[ "${#nodes[@]}" -ge 2 ]]; then 
            echo "devices_not_support=["
            for i in "${!nodes[@]}"; do
                if [[ $i != $target_idx ]]; then
                    echo "  \"${nodes[$i]}\" # Driver: ${drivers[$i]}"
                fi
            done
            echo "]"]
        fi
    fi
    if [[ -n "$vendor_node" || -z "$target_idx" ]]; then
        if [[ -z "$vendor_node" ]]; then
            # no NPU device
            echo "no_detected_npu=1"
        fi
        if [[ "${#nodes[@]}" -ge 1 ]]; then
            echo "devices_not_support=["
            for i in "${!nodes[@]}"; do
                echo "  \"${nodes[$i]}\" # Driver: ${drivers[$i]}"
            done
            echo "]"
        fi
    fi

    # runtime library
    echo -e "\n[libraries]"
    SO_LIST=("libteflon.so" "libvx_delegate.so" "librknn_delegate.so" "libarmnnDelegate.so")
    for i in "${!SO_LIST[@]}"; do
        #echo "$i ${SO_LIST[$i]}"
        so="$(find_lib ${SO_LIST[$i]})"
        ret=$?
        if [[ $ret == 0 ]]; then
            echo "delegate=\"$so\""
            break
        fi
    done 
    [[ $ret != 0 ]] && echo "no_delegate=1"

) | tee npu_env.toml
