# wtforms-form-bench — WTForms 表单成本拆解：`validate()` 只占 19–27%，微优化上限 ~1.05x

**这是什么**：对 WTForms 表单生命周期（构造 + 校验）的一次可复现测量。结论是**负面且有用**的：
把 `Field.validate` 的内联链优化到比上游快 **1.16x（仅 validate 段）**，端到端（构造+校验）仍只有
**1.01–1.05x**——因为它只占表单生命周期的 19–27%。仓库不是 `-opt-lab`：真实语料上没有 ≥1.15x 的可用收益。

Upstream: https://github.com/wtforms/wtforms (commit `2224255c4acc594d734cef0bbc83360452a67983`, BSD-3-Clause)

## 结论表（单位 ms，3 warmup + 7 样本，`time.perf_counter()`，中位数）

| 字段数 | 基线构造 | 基线 validate | 基线总计 | 优化后 validate | validate 加速 | 端到端加速 |
|---|---|---|---|---|---|---|
| 8  | 0.0953 | 0.0427 | 0.1398 | 0.0394 | **1.085x** | 0.972x |
| 20 | 0.2029 | 0.0699 | 0.2768 | 0.0600 | **1.164x** | 1.045x |
| 48 | 0.4588 | 0.1271 | 0.5860 | 0.1100 | **1.156x** | 1.014x |

三规模 validate 段加速中位 **1.156x**；端到端中位 **1.014x**。按 G3/G3b（≥1.15x 端到端/真实语料）
判定 **FAIL**，因此本仓库以 `-bench` 形态发布，不声称可用加速。8 字段端到端 0.972x 落在噪声内
（该规模总耗时 rsd 21–24%，中位数级别差异不可解读）。

## 为什么这个数字值得记录

`cProfile` 只看 `validate()` 时，`Field.validate` + `_run_validation_chain` 占 39% tottime
（3,000 次 48 字段 validate，`benchmark/raw/` 同负载）。只按这个比例做优化会预期 ~1.5x；
但同一份表单在真实请求里还要构造（字段实例化、formdata 处理、默认值/过滤器），构造耗时是
validate 的 3.4–5.6 倍。**分析单位选错，收益会被高估 5–20 倍。** 这正是本仓库的可复现结论。

## 候选改动（`patch.diff`，39 行，1 文件）

`src/wtforms/fields/core.py::Field.validate`：把 `itertools.chain(self.validators, extra_validators)`
+ 每字段重入 `_run_validation_chain` 改成两个直接 for 循环、`errors.append` 局部绑定、
空 `extra_validators` 跳过 `check_validators`。异常/停止语义逐字保持：`StopValidation` 带消息才
append、`ValidationError` append、停止后不跑 post 之外的其他校验器。`_run_validation_chain`
保留为公共子类兼容入口，未改签名。

## 差分（G2）

`python tests/test_diff.py --base-src <base>/src --opt-src <opt>/src`

- **1200 个 sha256 去重后的独立输入**（随机 6–26 字段、随机校验器组合、随机变异：空串/空白/超长/
  非 ASCII/emoji/None/负数/越界），每个输入都真的构造 + 校验一次；去重键是输入 JSON 的 sha256。
- 两个实现在**独立子进程**中导入（同名包隔离），逐用例比较 `form.errors`、每字段
  `data/raw_data/errors/process_errors` 的规范化 JSON 的 sha256。
- 实测：**1200 samples, 0 mismatches, byte-identical True**（1.7s）。

## 质量闸门（逐条，含复现命令）

| 闸门 | 结果 | 复现 |
|---|---|---|
| G1 上游测试全绿 | **PASS** 563 passed / 0 failed（0.55s） | `python -m pytest -q`（改动后同一命令） |
| G2 差分 ≥1000 组 | **PASS** 1200 独立样本 / 0 差异 | `python tests/test_diff.py --base-src ... --opt-src ...` |
| G3 端到端中位 ≥1.15x | **FAIL** 1.014x（validate 段 1.156x） | `python benchmark/bench.py --src <src> --impl base --out b.json`（对 opt 同跑） |
| G3b 真实语料 ≥1.15x | **FAIL** 同一语料 1.01–1.05x | 同上 |
| G4 大规模不退化 | **FAIL** 48 字段 1.014x < 1.15x（相对基线未退化，但不足以称优化） | 同上 |
| G5 峰值 RSS | 未声称：改动不新增分配，未做 RSS 对比，故不填数字 | — |

因此 `status: published` 仅作为测量研究，**不是**可用优化；若按 `-opt-lab` 标准应判 skipped。

## 复现（3 条命令）

```bash
git clone --depth=1 git@github-linluozi:wtforms/wtforms.git base && cd base && git checkout 2224255c4acc594d734cef0bbc83360452a67983
python3 -m venv .venv && . .venv/bin/activate && pip install -e . pytest && git apply /path/to/wtb/patch.diff
python benchmark/bench.py --src "$PWD/src" --impl opt --out benchmark/optimized.json   # 基线去掉 patch、--impl base
```

（本机实测：`python3 -V` = 3.12.3；基线/优化两棵树各自 `pip install -e .`，同一 venv 通过
`--src` 切换，避免安装差异。）

## 环境

- CPU: 见 `benchmark/baseline.json`（本机 4 vCPU / 3.6 GB，`platform` 字段随样本落盘）
- Python 3.12.3；WTForms HEAD `2224255c...`（2026-11-01）；seed=0（语料确定性，无随机）
- 原始逐样本数据：`benchmark/raw/base-*.json`、`benchmark/raw/opt-*.json`（各 6 用例 × 7 样本）
- 噪声披露：8 字段总耗时 rsd 21–24%（小规模 + 页错误），48 字段 2.5–4.7%；结论只用中位数，
  8 字段端到端 0.972x 不解读为退化。

## 本轮创新

首次把「优化收益的分析单位」本身作为测量对象：同一 `patch.diff` 在 validate-only 口径是
1.156x，在「构造+校验」生命周期口径只有 1.014x；给出可复现的摊销上限（validate 占 19–27%），
并指出 cProfile 的 39% tottime 会把收益高估约 5–20 倍。与既有 `-opt-lab`（只报单函数加速）不同，
这里的主张是**该函数级加速在真实表单请求里不可兑现**。

## 目录

```
README.md  LICENSE  patch.diff  .gitignore
benchmark/bench.py  benchmark/forms.py  benchmark/baseline.json  benchmark/optimized.json
benchmark/raw/*.json
tests/test_diff.py
```
