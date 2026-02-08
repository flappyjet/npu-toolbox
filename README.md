# npu-toolbox
tools for NPUs on edge computing devices

Devices with NPU:
| Vendor | SoC / Chip Series | NPU capabilty (INT8) | Kernel Module | Device Node | Common Devices |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Rockchip** | RK3588 / RK3588S | **6.0 TOPS** | `rknpu.ko` / `rocket.ko` | `/dev/rknpu` / `/dev/accel/accel*` | Banana Pi M7, Khadas EDGE2, NanoPC T6 LTS, NanoPi M6, NanoPi R6S/R6C, Orange Pi 5/5 Plus, Radxa Rock 5A/5B/5C/5 ITX/5T |
| **Rockchip** | RK3566 / RK3568 | **1.0 TOPS** | `rknpu.ko` | `/dev/rknpu` | Nanopi R3S LTS, Odroid M1, Radxa Zero 3W/3E |
| **Amlogic** | A311D | **5.0 TOPS** | `galcore.ko` / `etnaviv.ko` | `/dev/galcore` / `/dev/dri/renderD*` | Banana PI CM4-IO, Banana PI M2S (部分型号), Khadas VIM3, Khadas VIM3L |
| **Amlogic** | S905D3 | **1.2 TOPS** | `galcore.ko` | `/dev/galcore` |  Beelink GT-King |
| **NXP** | i.MX 8M Plus | **1.0 TOPS** | `galcore.ko` | `/dev/galcore` | Coral Dev Board, Toradex Verdin |
| **NXP** | i.MX 93 | **1.0 TOPS** | `ethos_u.ko` | `/dev/ethosU*` | i.MX 93 Evaluation Kit, Industrial Gateways |
