# 翻译差分测试 / Translation differential tests

## A. 整数语义（`IntegerABI` vs 原生 C + UBSan）

- 用例 / cases: 1200，种子 / seed: 1
- 编译器 / compiler: `gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`
- 参数 / flags: `-O0 -std=c99 -w -fsanitize=undefined -fno-sanitize-recover=undefined -fno-sanitize=alignment`

| 结论 | 例数 |
|---|---|
| agree | 1199 |
| model too strict | 1 |

不一致的例子（最多 10 个）:

- `(-(((unsigned short)(((0x7fffffff) + (((unsigned short)-2)))))))` → 模型 None / 原生 exit=0 out='-65533' ub=False

## B. 循环翻译（`translate_c` + 重放 vs 原生 C）

- 程序 / programs: 80，每程序输入 / inputs each: 12，种子 / seed: 2
- 编译器 / compiler: `gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`

| 结论 | 例数 |
|---|---|
| agree | 1095 |
| outside no-overflow domain | 185 |

另有每程序 4 次输入被刻意放到 `int` 边界之外（`2^31-1`、`-2^31` 等）。这些行记作“越界”，不计为翻译错误——它们正是证书里那条 no-overflow 义务要排除的区域。

## A′. 那一例不一致到底是什么 / the single disagreement, probed

被测表达式：`-(unsigned short)(0x7fffffff + (unsigned short)-2)`——`int + int` 溢出。同一表达式在四种操作数来源下的编译结果：

| 操作数来源 | exit | 输出 | UBSan 报错 |
|---|---|---|---|
| parameters (as the harness calls it) | 0 | -65533 | 否 |
| volatile locals | 0 | -65533 | 否 |
| plain locals, constant initialisers | 0 | -65533 | 否 |
| plain locals, through argv | 0 | -65533 | 否 |

