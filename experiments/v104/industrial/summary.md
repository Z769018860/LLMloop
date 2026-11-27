# v1.04 E3 工业代码覆盖边界 / industrial coverage boundary

四个基座、四个版本、由归档哈希钉住；文件按路径的 sha256 升序预注册抽样，抽样发生在任何
验证结果之前。三段分母严格嵌套：**有循环的函数 ⊇ 片段内候选 ⊇ 真的证出**。
Four bases pinned by archive hash; files sampled by ascending sha256 of the path, chosen
before any result existed. Three strictly nested denominators: loop functions ⊇ fragment ⊇ proved.

| 项目 / project | 抽样文件 | 解析成功 | 函数 | 含循环 | 片段内候选 | 证出 |
| --- | --- | --- | --- | --- | --- | --- |
| busybox | 323 | 323 | 1308 | **501** | 4 | **0** |
| openssl | 400 | 398 | 3644 | **506** | 2 | **0** |
| sqlite | 128 | 128 | 3422 | **917** | 2 | **0** |
| aws-c-common | 41 | 41 | 570 | **161** | 0 | **0** |
| **合计 / total** | **892** | **890** | **8944** | **2085** | **8** | **0** |

## 一句话 / in one line

**2085 个含循环的函数里，第一处阻塞是内存（指针/数组/成员）的占了 2067 个（99%）**；片段内的标量候选 8 个，最终证出 0 个。

**Of 2085 loop-bearing functions, 2067 are stopped first by memory (pointers, arrays, members)**; 8 reach the scalar fragment and 0 are proved.

## 每一级为什么掉下去 / why each stage drops

### busybox

解析失败 / parse failures: —

片段外的第一处阻塞 / first blocking feature: pointers_arrays_or_members 489, calls_to_other_functions 5, scalar_loop_candidate 4, goto 3

候选的结局 / candidate outcomes: REJECTED_FRONTEND 2, NO_SAMPLES 1, STUCK 1

### openssl

解析失败 / parse failures: TOO_LARGE 2

片段外的第一处阻塞 / first blocking feature: pointers_arrays_or_members 503, scalar_loop_candidate 2, calls_to_other_functions 1

候选的结局 / candidate outcomes: REJECTED_FRONTEND 1, STUCK 1

### sqlite

解析失败 / parse failures: —

片段外的第一处阻塞 / first blocking feature: pointers_arrays_or_members 915, scalar_loop_candidate 2

候选的结局 / candidate outcomes: REJECTED_FRONTEND 2

### aws-c-common

解析失败 / parse failures: —

片段外的第一处阻塞 / first blocking feature: pointers_arrays_or_members 160, calls_to_other_functions 1

候选的结局 / candidate outcomes: 

## 这条数字能说什么 / what the numbers support

- “含循环的函数”是分母，抽样规则与哈希都在 `protocol.json` 里，可逐文件复算。
- 片段内候选是**语法**上的：标量整数、无指针/数组/结构体/浮点/goto/函数调用。
- “证出”指 `houdini_loops` 在**参数类型的完整取值范围**上返回 PROVED；没有收窄参数窗口。
- 这一节不含第三方见证复核（E1 在 SV-COMP 语料上做了这件事），所以它测的是**覆盖面**，
  不是**可靠性**。
- 与 SV-COMP 的 400 例不可混算：那边是同一族程序上的对照，这里是工业代码上的边界。

