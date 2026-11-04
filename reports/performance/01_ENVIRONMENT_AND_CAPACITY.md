# 01 — ENVIRONMENT AND CAPACITY AUDIT

## 1. Executive Overview

This report provides the exhaustive forensic baseline of the host hardware, virtualization environment, operating system kernel, storage subsystems, network interfaces, and container resource boundaries hosting the Oxmit Telegram video compression platform.

The system is deployed on an **Amazon Web Services (AWS) Lightsail** virtual machine instance located in the `us-east-2` (Ohio) region.

---

## 2. Host Compute Architecture (CPU)

### 2.1 Processor Specifications
- **Processor Model**: Intel(R) Xeon(R) Platinum 8275CL CPU @ 3.00GHz
- **Microarchitecture**: Intel Cascade Lake-SP (Server Platform, 14nm)
- **Virtual CPU Count**: 8 vCPUs (assigned via AWS Xen/KVM Nitro hypervisor)
- **Topology**: 1 Socket, 4 Physical Cores, 2 Threads per Core (Hyperthreading enabled)
- **Base Frequency**: 3,000.000 MHz (3.00 GHz)
- **BogoMIPS**: 6,000.00
- **Virtualization Type**: Full virtualization (`HVM`, hypervisor-managed)

### 2.2 Cache Hierarchy
- **L1 Data Cache**: 128 KiB (4 instances of 32 KiB per core)
- **L1 Instruction Cache**: 128 KiB (4 instances of 32 KiB per core)
- **L2 Cache**: 4,096 KiB (4 instances of 1,024 KiB per core)
- **L3 Unified Cache**: 36,608 KiB (~35.75 MiB shared across package)

### 2.3 Instruction Set & Vector Extensions
The processor features full support for modern multimedia vector extensions, including:
- **AVX (Advanced Vector Extensions)**: 256-bit wide SIMD registers.
- **AVX2**: 256-bit integer vector operations, FMA3 (Fused Multiply-Add).
- **AVX-512**: Specifically `avx512f` (Foundation), `avx512dq` (Doubleword & Quadword), `avx512cd` (Conflict Detection), `avx512bw` (Byte & Word), and `avx512vl` (Vector Length extensions).
- **Hardware Cryptography**: `aes`, `pclmulqdq`, `rdrand`, `rdseed`.

> [!NOTE]
> FFmpeg and `libx264` / `libx265` build assemblies automatically detect AVX2 and AVX-512. However, AVX-512 execution on Cascade Lake can trigger dynamic core frequency downclocking (thermal frequency throttling) when all 8 vCPUs run wide 512-bit vector instructions simultaneously.

---

## 3. Host Memory (RAM) & Swap Subsystem

### 3.1 Memory Capacity & Allocation
- **Total Physical Memory**: 15,984,388 KiB (~15.24 GiB / 16.0 GB advertised)
- **Active / Used Memory**: ~2,500 MiB under idle/baseline load
- **Available Memory**: ~13,100 MiB (~84% head room available for active workloads)
- **Buffers / Page Cache**: ~1,800 MiB utilized for Linux disk caching

### 3.2 Swap Analysis
- **Configured Swap**: **0 KiB (No swap partition or file configured)**
- **Forensic Risk**:
  In high-concurrency scenarios (e.g., multiple workers transcoding 4K or 1080p high-bitrate media simultaneously), memory spikes that exceed 15.24 GiB will immediately trigger the Linux Kernel Out-Of-Memory (`oom-killer`), resulting in abrupt termination of FFmpeg or Docker worker processes (`SIGKILL`, exit code 137).

---

## 4. Storage Subsystem & Measured I/O Throughput

### 4.1 Storage Hardware
- **Disk Type**: Amazon Elastic Block Store (EBS) exposed over NVMe interface (`/dev/nvme0n1p1`).
- **NVMe Controller**: Amazon.com PCIe SSD Controller (`Amazon Device 1111` / `Elastic Block Store NVMe`).
- **Filesystem**: `ext4` with `rw,relatime,discard,errors=remount-ro` options.
- **Total Capacity**: 619 GiB.
- **Used Space**: 40 GiB (6%).
- **Free Space Available**: 579 GiB.

### 4.2 Measured Empirical I/O Benchmarks
Direct disk I/O was measured on-host using non-cached direct block writes and reads (`dd oflag=direct` / `iflag=direct`, 1024 MB transfer):

| Benchmark Test | Block Size | Total Volume | Elapsed Time | Measured Throughput | Average Block Latency |
|---|---|---|---|---|---|
| **Sequential Write (Direct I/O)** | 1,048,576 bytes (1 MiB) | 1,073,741,824 bytes (1.0 GiB) | 7.198 s | **149 MB/s** (~1,192 Mbps) | 6.83 ms |
| **Sequential Read (Direct I/O)** | 1,048,576 bytes (1 MiB) | 1,073,741,824 bytes (1.0 GiB) | 8.214 s | **131 MB/s** (~1,048 Mbps) | 7.82 ms |

### 4.3 Storage Forensic Conclusion
Video compression streaming rates at 1080p typically generate **2 MB/s to 10 MB/s** of read/write bandwidth. At 149 MB/s write throughput, the physical storage layer is operating at less than **7% of maximum continuous saturation**. Disk I/O throughput is definitively **NOT** a bottleneck for single or dual worker encoding.

---

## 5. Network Subsystem

### 5.1 Host Interfaces
- **Primary NIC**: `ens5` (Amazon Elastic Network Adapter - ENA).
- **MTU**: 9,001 bytes (AWS Jumbo Frames enabled inside AWS VPC).
- **Virtual Interfaces**: `docker0` bridge (172.17.0.1) and internal Compose bridge `br-58c9735d4ff0` (172.18.0.1) at MTU 1,500.

### 5.2 Network Latency to Telegram Bot API
- Target: `api.telegram.org` (HTTP/2 / HTTPS via AWS outbound gateway).
- Measured Ping / TCP Handshake: ~8.5 ms to 12.1 ms.
- Bot API local server: `oxmit-botapi` is deployed locally in Docker, allowing direct local file streaming to Telegram without intermediate HTTP payload roundtrips for large files.

---

## 6. Docker Container Resource Boundaries & Cgroups

The Oxmit system runs inside Docker Compose with the following container cgroup boundaries verified from inspect metadata:

| Container Name | Service Role | CPU Quota (NanoCPUs) | Memory Limit | Memory Reservation | Pids Limit |
|---|---|---|---|---|---|
| `oxmit-encore-worker-1` | Primary Transcoding Worker | **7,000,000,000** (7.0 vCPUs) | **4,831,838,208** (4.50 GiB) | **1,073,741,824** (1.00 GiB) | Unlimited |
| `oxmit-encore-worker-2` | Secondary Worker | 7,000,000,000 (7.0 vCPUs) | 4,831,838,208 (4.50 GiB) | 1,073,741,824 (1.00 GiB) | Unlimited |
| `oxmit-encore-web` | Transcoding Coordinator | Uncapped | Uncapped | Uncapped | Unlimited |
| `oxmit-bot` | Python Application | Uncapped | Uncapped | Uncapped | Unlimited |
| `oxmit-botapi` | Local Telegram Bot API | Uncapped | Uncapped | Uncapped | Unlimited |
| `oxmit-postgres` | PostgreSQL DB | Uncapped | Uncapped | Uncapped | Unlimited |
| `oxmit-redis` | Redis Broker | Uncapped | Uncapped | Uncapped | Unlimited |

### 6.1 Worker CPU Quota Contention
Both `oxmit-encore-worker-1` and `oxmit-encore-worker-2` are each provisioned with a `NanoCPUs` quota of 7.0 cores.
- If **1 worker** is active: It can consume up to 7.0 cores (~700% CPU in `top`).
- If **2 workers** run concurrently: Both workers compete for the host's 8 physical vCPUs. Linux Completely Fair Scheduler (CFS) time-slices the 8 vCPUs between them, reducing effective compute per worker to **~3.5 - 3.8 vCPUs**, cutting each worker's encoding speed by **~45%**.
