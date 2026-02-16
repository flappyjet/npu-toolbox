# npu-toolbox
tools for NPUs on edge computing devices

## Devices with NPU:
| Vendor | SoC / Chip Series | NPU capabilty (INT8) | Kernel Module | Device Node | Common Devices |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Rockchip** | RK3588 / RK3588S | **6.0 TOPS** | `rknpu.ko` / `rocket.ko` | `/dev/rknpu` / `/dev/accel/accel*` | Khadas EDGE2, Banana Pi M7, Banana PI W3，NanoPC T6 LTS, NanoPi M6, NanoPi R6S/R6C, Orange Pi 5/5 Plus, Radxa Rock 5A/5B/5C/5 ITX/5T |
| **Rockchip** | RK3576 | **6.0 TOPS** | `rknpu.ko` / `rocket.ko` | `/dev/rknpu` / `/dev/accel/accel*` | Banana PI M5-Pro, NanoPi M5, NanoPi R76S, Radxa Rock 4D |
| **Rockchip** | RK3566 / RK3568 | **1.0 TOPS** | `rknpu.ko` | `/dev/rknpu` | Banana PI M4S, Banana PI R2-Pro, Nanopi R3S LTS, Odroid M1, Radxa Zero 3W/3E |
| **Amlogic** | A311D | **5.0 TOPS** | `galcore.ko` / `etnaviv.ko` | `/dev/galcore` / `/dev/dri/renderD*` | Khadas VIM3, Banana PI CM4, Banana PI M2S([tips](https://docs.banana-pi.org/en/BPI-M2_Super/BananaPi_BPI-M2_Super)), OneThingCloud OES |
| **Amlogic** | A311D2-N0D | **3.2 TOPS** | `galcore.ko` | `/dev/galcore` | Khadas New VIM4 with NPU([tips](https://docs.khadas.com/products/sbc/vim4/start)) |
| **Amlogic** | S905D3 | **1.2 TOPS** | `galcore.ko` | `/dev/galcore` | Khadas VIM3L |
| **NXP** | i.MX 8M Plus | **1.0 TOPS** | `galcore.ko` | `/dev/galcore` | Coral Dev Board, Toradex Verdin |
| **NXP** | i.MX 93 | **1.0 TOPS** | `ethos_u.ko` | `/dev/ethosU*` | i.MX 93 Evaluation Kit, Industrial Gateways |

## How data flow to NPU:

User's Program

   ↓

Glue Layer (Delegate)

   ↓

Runtime Library (Inference Engine)

   ↓

Kernel Module (Driver)

   ↓

NPU Hardware (Soc)


## Different implementation comparison:

### Vendor (Amlogic) vs. Mainline (Linux)

| Layer | Vendor Stack | Linux (Mainline) Stack |
| :--- | :--- | :--- |
| **User's Model File** | AI Application (TFLite, ONNX) | AI Application (TFLite) |
| **Glue Layer** | `libvx_delegate.so` | `teflon.so` (TFLite Delegate) |
| **Runtime** | `libtim-vx.so`, `libOpenVX.so` | `libgallium.so` (Mesa) |
| **Kernel Module** | `galcore.ko` (for kernel 4.9, 5.15) | `etnaviv.ko` |
| **Hardware** | A311D NPU (Vivante VIP8000) | Same | 

---

### Vendor (Rockchip) vs. Mainline (Linux)

| Layer | Rockchip (Vendor) Stack | Linux (Mainline) Stack |
| :--- | :--- | :--- |
| **User's Model File** | AI Application (.rknn) | AI Application (TFLite, ONNX) |
| **Glue Layer** | `librknn_delegate.so` | `teflon.so` (TFLite Delegate) |
| **Runtime** | `librknnrt.so`, `librkllmrt.so` | `libgallium.so` (Mesa) |
| **Kernel Module** | `rknpu.ko` (v0.9.8) | `rocket.ko` |
| **Hardware** | RK3588 NPU (3-Core Design) | Same | 

---

*Implementation Details*

The Amlogic vendor stack relies on the Vivante `galcore` kernel module. It uses the ION memory allocator or DMA-BUF to share buffers between the CPU and NPU, ensuring zero-copy data transfer during inference.

The Rockchip vendor driver `rknpu` is licensed under GPL v2 and typically integrates deeply with Rockchip's specialized memory management for performance. The vendor stack uses specialized GEM (Graphics Execution Manager) objects to manage memory across different cores and cache types like SRAM or NBUF.

The community-driven drivers (eg. `rocket`, `etnaviv`) aim for integration with standard Linux subsystems like `accel` for broader compatibility at the cost of some vendor-specific optimizations.


## Some Guides:
* https://github.com/airockchip/rknn-toolkit2
* https://github.com/airockchip/rknn-llm
* https://docs.khadas.com/products/sbc/vim3/npu/vx-tflite
* https://www.nxp.com.cn/docs/en/user-guide/IMXMLUG.pdf
