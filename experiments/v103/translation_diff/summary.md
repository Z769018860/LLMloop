# 翻译差分测试 / Translation differential tests

## A. 整数语义（`IntegerABI` vs 原生 C + UBSan）

- 用例 / cases: 1000，种子 / seed: 1
- 编译器 / compiler: `gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`
- 参数 / flags: `-O0 -std=c99 -w -fsanitize=undefined -fno-sanitize-recover=undefined -fno-sanitize=alignment`

| 结论 | 例数 |
|---|---|
| agree | 999 |
| model too strict | 1 |

不一致的例子（最多 10 个）:

- `(-(((unsigned short)(((0x7fffffff) + (((unsigned short)-2)))))))` → 模型 None / 原生 exit=0 out='-65533' ub=False

## B. 循环翻译（`translate_c` + 重放 vs 原生 C）

- 程序 / programs: 80，每程序输入 / inputs each: 12，种子 / seed: 2
- 编译器 / compiler: `gcc (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`

| 结论 | 例数 |
|---|---|
| agree | 960 |

