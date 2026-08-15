# 固件/二进制/逆向 工具配置（2026-08-12 装好）

## 已装工具

### 反编译/逆向
- **ghidra** 11.3.2 — `/opt/homebrew/bin/ghidraRun` → 强反编译（Go/Rust/C/裸 ELF 最佳）
- **radare2** — `r2` / `radare2`，命令 `r2 -A -q -c 'afl; pdf @ main' binary`
- **gdb** 16.3 — `gdb binary`，动态调试

### 固件提取
- **binwalk** 3.1.0 — `binwalk -e firmware.bin -C extract_dir`
- **7z** / **unzip** — 解压多种容器
- **file** / **strings** / **objdump** / **nm** / **xxd** / **hexdump** — 基础分析

### Python 库
- **pwntools** — `from pwn import *`，pwn 框架（远程/ROP/exploit）
- **angr** 9.3.0 — 符号执行 / 自动化漏洞挖掘 / z3 求解

### QEMU（跨架构跑固件）
- qemu-system-x86_64 / qemu-system-aarch64 / qemu-system-arm / qemu-system-mips / qemu-system-mipsel / qemu-system-ppc / qemu-system-riscv64 / qemu-system-sparc 等
- 注意：brew qemu 是 system 模式，user 模式无 static 版（macOS 限制）
- 替代：用 chroot 跑 / 用静态二进制版 qemu（如果 docker 里跑）

## 工作流（固件题通用）

### 1. 探测 + 抓样本
```bash
# 端口探测（9101-9108 是 f1/f2 系列）
for p in 9101 9102 9103 9104 9105 9106 9107 9108; do
  timeout 1 bash -c "echo > /dev/tcp/TARGET/$p" 2>/dev/null && echo "  $p OPEN"
done
# banner
nc -w 2 TARGET PORT
(echo help; sleep 1) | nc TARGET PORT
# 下载固件/二进制
curl -s -o /tmp/fw.bin http://TARGET:PORT/download
file /tmp/fw.bin
checksec --file=/tmp/fw.bin 2>/dev/null  # 看 PIE/RELRO/NX/Canary
```

### 2. 固件提取
```bash
binwalk -e /tmp/fw.bin -C /tmp/fw_extract
ls /tmp/fw_extract/_*  # 提取的文件系统
# 或 7z
7z x /tmp/fw.bin -o/tmp/fw_extract
```

### 3. 逆向
```bash
# 1) strings 找关键字
strings /tmp/fw.bin | grep -iE "flag|key|admin|pass|secret|serial|license|FNV|CRC|sha|md5|aes|rsa" | head

# 2) r2 自动化分析
r2 -A -q -c 'afl; pdf @ main' /tmp/fw.bin | head -200
# afl = 列出所有函数
# pdf @ main = 反编译 main 函数
# pdf @ sym.check = 反编译 check 函数
# iz~0x4010 = 读 0x4010 地址（XOR blob 位置）

# 3) ghidra 强反编译
ghidraRun /tmp/fw.bin  # 交互式，headless 模式可批处理
```

### 4. 漏洞分析 + Exploit
```python
# pwntools 远程 fuzz / pwn
from pwn import *
r = remote('TARGET', PORT)
print(r.recv(1024))  # banner
# 试长 buffer
r.sendline(b'A' * 1024)
print(r.recv(1024))
# 试 SETBUF 长度边界
for n in [0, 1, 8, 16, 32, 64, 128, 256, 512, 1024]:
    r = remote('TARGET', PORT)
    r.sendline(f'SETBUF {n}'.encode())
    print(n, r.recv(1024))
```

### 5. 符号执行（angr / z3 求解）
```python
import angr
from z3 import *

# FNV-1a-32 反算 serial 示例
PRIME = 0x01000193
SEED  = 0x811c9dc5
TARGET = 0xe868c44d
solver = Solver()
bytes_serial = [BitVec(f'b{i}', 8) for i in range(32)]
h = SEED
for b in bytes_serial:
    h = (h ^ b) & 0xffffffff
    h = (h * PRIME) & 0xffffffff
solver.add(h == TARGET)
for b in bytes_serial:
    solver.add(b >= 0x20, b <= 0x7e)
if solver.check() == sat:
    m = solver.model()
    serial = bytes([m[b].as_long() for b in bytes_serial])
    print('serial:', serial)
```

## 协议模式（f1/f2 系列常见）

### f1 系列（f1-01~f1-05）buffer 服务
- 端口 9101-9108
- 协议：STORE A*64 / LIST / HIST / HEARTBEAT / SETPAYLOAD / DUMP / BUILD / SETBODY / ADDHEADER
- 漏洞：长 token OOB / eviction 邻接内存 / hdrtab uninit read

### f2 系列（f2-01~f2-08）固件 + license
- 端口 9101-9108
- 协议：text 协议（help / submit flag string / read flag）
- 漏洞：license 校验反解 / FNV-1a-32 / CRC32 / AES / RSA

## 工具使用纪律

1. **先 strings + file**（10 秒快速识别）
2. **binwalk -e** 提取固件文件系统（30 秒）
3. **r2 -A** 自动分析找 main（10 秒）
4. **ghidra** 强反编译（5 分钟，但看复杂逻辑必须用）
5. **pwntools** 远程交互 + fuzz（快速定位漏洞）
6. **angr** 符号执行 / z3 求解（解 license / 找 flag 路径）
7. **绝对不要 nmap -p-**（题目说不要大规模端口扫描）
