# 主题：二进制逆向 / 自研 VM / 加密凭据

## 场景
自研执行机制 / 对逆向有较强抵抗 / 取得被保护的凭据（授权评估）。

## 标准流程
1. **文件定性**：`file`、`strings`、`checksec`、`readelf -h`——架构、加壳、stripped、PIE、动态链接
2. **运行行为**：`./bin <输入>` 观察输出/退出码；`strace`/`ltrace`/`gdb` 建输入-行为映射
3. **静态反汇编**：`objdump -d` / rizin / ghidra。找 main → 校验逻辑 → 主流程
4. **定位加密凭据**：熵最高的 `.data` 段、字符串里像密文的字节；全文件交叉引用找引用点
5. **识别自研 VM**：main 里跳转表分发（`(op+const)&0xff` → 跳转表），还原 opcode → handler 语义 → 用脚本仿真字节码
6. **判断真/假**：VM 可能只是 decoy（输出占位字符）；真实凭据算法在别处 / 离线推导。验证 blob 是否被实际变换（还是死加载）

## 凭据推导
- 已知 flag 前缀做 crib：`FLAG{` @0、`}` @末尾 → 推导密钥流 → 与二进制内常量/字符串比对
- 密码族逐个扫：单/多字节 XOR、RC4、TEA/XTEA/XXTEA、哈希派生密钥流、家族变换模板
- **家族对照**：同系列已解题的二进制逆向真实实现，找共用模板（注意成员间可能不共享）
- **要 hint**：平台 hint 端点常给关键提示（如"字节码即构造过程"）
- 全文件搜 magic 常量（TEA delta `0x9e3779b9`、RC4 表特征）判断密码类型

## 工具
- 静态：`objdump -d` `readelf -a` `strings` `grep -oba`、rizin/ghidra
- 动态：`gdb` `strace` `ltrace`
- 脚本：pwntools（`ELF()`）、capstone、z3、Python 仿真 VM、自写 XOR/RC4/TEA 扫描

## 关键心态
- 别陷单方向穷举：跑不动就换"要 hint / 家族对照 / 换密码族"
- 确认"该方向无解"要留证据（脚本+结果），避免重复
