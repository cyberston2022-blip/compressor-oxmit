# 03 — Current Runtime Baseline & Infrastructure Audit

## 1. Hardware Specifications
- **Host**: AWS Lightsail Virtual Private Server (Instance ID: `18.227.142.205`, us-east-2)
- **CPU**: 8 vCPUs (Intel Xeon Platinum 8175M / AMD EPYC 7R12 base), 2.50 GHz
- **RAM**: 16 GB Total Memory (Available: $\approx 13.2\text{ GB}$)
- **Storage**: 320 GB NVMe SSD mounted at `/` (Available free space: $>180\text{ GB}$)
- **OS**: Ubuntu 24.04.1 LTS (Linux 6.8.0-1017-aws x86_64)

## 2. Active Services & Architecture
```mermaid
graph TD
    User([Telegram User]) <--> BotAPI[oxmit-botapi :8081]
    BotAPI <--> Bot[oxmit-bot :8080/8091]
    Bot <--> PG[(PostgreSQL 16 :5432)]
    Bot <--> Redis[(Redis 7 :6379)]
    Bot <--> EncoreWeb[oxmit-encore-web :8080]
    EncoreWeb <--> Worker1[oxmit-encore-worker-1]
    EncoreWeb <--> Worker2[oxmit-encore-worker-2]
    Worker1 <--> SharedMedia[/media/out & /media/incoming]
    Worker2 <--> SharedMedia
```

## 3. Container Resource Allocations
- `oxmit-bot`: Unrestricted CPU / 1 GB memory limit.
- `oxmit-postgres`: 2 GB memory limit, shared buffers 512 MB.
- `oxmit-redis`: 256 MB memory limit.
- `oxmit-encore-web`: Spring Boot JVM 512 MB heap.
- `oxmit-encore-worker-1` & `worker-2`: Managed dynamically by `WorkerCpuTuner`:
  - Idle/Single job: 7.0 vCPUs.
  - Two concurrent jobs: 3.2 vCPUs each.
