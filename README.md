# npu-toolbox
tools for NPUs on edge computing devices

Devices with NPU:
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

