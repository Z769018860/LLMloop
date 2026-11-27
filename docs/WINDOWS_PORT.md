# 在 Windows 上跑冻结的实验臂 / running the frozen arms on Windows

> 一句话：**验证器一个字节都没动**；动的是"谁来包住子进程并记录它花了多少"。
> 这个区别必须写在论文里，因为它决定了"验证器未改"这句话还成不成立。

## 0. 为什么会有这件事

三个臂（E6b 补 void、E6d 第二价位、E6e 重复一致性）原本设计在 GitHub Actions 的 `ubuntu-latest`
上跑。这台机器上没有 `gh`、没有 `GITHUB_TOKEN`，无法派发 workflow，所以改在本地 Windows 跑。

第一次尝试**在发出任何 LLM 请求之前就崩了**，249 个单元全部 `HARNESS_ERROR`：

```
AttributeError: module 'os' has no attribute 'wait4'. Did you mean: 'write'?
```

`os.wait4`、`os.killpg`、`signal.SIGKILL` 都是 POSIX 专有，Windows 没有。它们全部来自
`scripts/resource_capture.py` —— 这个文件在每一臂的 `frozen_source_sha256` 里。

好在崩溃发生在 `capture()` 的第一行，`ask` 子进程还没起，所以那 233 个 `HARNESS_ERROR` 行
每行的 `calls` 都是 **0**：**零次 LLM 调用，零花费**。

## 1. 为什么不改 `resource_capture.py`

改它三行就能修好。但它的 sha256 被写在 `experiments/v10{5,6,7}/…/protocol.json` 的
`frozen_source_sha256` 里，而论文的中心主张是"**验证器一行未改**"。改一个字节，"未改"就变成
"改了但只改了记录部分"——后者是正确的但需要一整段解释，而前者不需要解释。

所以修法是在**外面**补：`tools/wincompat/sitecustomize.py`。

```
PYTHONPATH=tools/wincompat python scripts/spec_v106.py run --workers 4
```

Python 启动时自动 import `sitecustomize`，在 runner 之前把三个名字装上：

| POSIX 名字 | Windows 上的实现 | 备注 |
| --- | --- | --- |
| `os.wait4(pid, WNOHANG)` | 轮询创建该 pid 的 `Popen`（`subprocess.Popen.__init__` 被 hook 记录） | 未退出返回 `(0, 0)`；退出后返回一次 pid，之后 `(0, 0)` |
| `os.killpg(pgid, sig)` | `psutil` 递归 kill 进程树 | 进程不在时抛 `ProcessLookupError`，与原语一致 |
| `signal.SIGKILL` | `= signal.SIGTERM` | Windows 没有 SIGKILL |
| `os.WNOHANG` | `= 1` | 只是透传，shim 从不阻塞 |

## 2. 三个真实的行为差异（不藏）

1. **`cpu_user_seconds` / `cpu_system_seconds` 可能是 `0.0`。** 进程退出后 Windows 往往已经
   回收句柄，`psutil` 读不到 CPU 时间。POSIX 下 `wait4` 的 `rusage` 一定能给。
   → **受影响**：`command.json` 里的 CPU 两列。
   → **不受影响**：`wall_seconds`、`sampled_peak_group_rss_bytes`、`resource_samples`，这三个来自
   `capture` 自己的 0.1 s 采样循环，与 `wait4` 无关。
2. **被信号杀死时 `exit_code` 是正数而不是负数。** POSIX 记 `-15`，这里记 `15`。
   代码里没有任何判定读这个字段（只用 `stop_reason`），所以不影响任何一行结果。
3. **同一个 pid 只能被 wait 一次。** POSIX 会 reap，shim 只是把 pid 从表里删掉。
   `capture` 的循环正是"等到 pid 回来就 break"，符合这个用法。

## 3. 这对结论意味着什么

- **不影响**：任何 `PROVED` / `UNKNOWN` / `VACUOUS` / `MALFORMED` 判定。这些由 `llmloop` 给出，
  `llmloop/` 与 `resource_capture.py` 都未改动，哈希在 `check` 里逐个比对通过。
- **影响**：三臂的 `command.json` 里 CPU 时间可能为 0。总账（`docs/LLM_LEDGER.md`）用的是
  token 与墙钟，不用 CPU 时间，所以**不进入任何金额**。
- 该记的地方：三份新协议（`v1.08/e6d`、`v1.09/e6e`）的 `protocol.json` 里没有这个字段——
  它不是协议变量，是执行环境。所以记在这里，并在论文的复现节加一句。

## 4. 复跑

```bash
cd H:/WorkBuddy/work/llmloop
export LLM_API_KEY=...                       # 不落盘、不进仓库
export PYTHONPATH=tools/wincompat            # 只在 Windows 上需要

python scripts/spec_v108.py check            # 字节还是不是冻结时那些字节
python scripts/spec_v108.py run --workers 4
python scripts/spec_v108.py merge
```

在 Linux / CI 上跑时**不要**设 `PYTHONPATH=tools/wincompat`：那层 shim 自己会判断
`sys.platform == 'win32' and not hasattr(os, 'wait4')`，在 POSIX 上是空操作，但显式不加载更干净。
