# 盲审评分表

每版一条，写在 `docs/reviews/<version>/score.json`。首版只建立基线，后续版本用 `--baseline` 对比总分，下降即 FAIL。

## 结构

```json
{
  "version": "v13",
  "reviewer": "实际执行盲审的代理或人",
  "scores": {"action": 9, "pacing": 8, "framing": 8, "quality": 8, "audio": 8},
  "p0": ["F470 收刀未完成，主体动作错位"],
  "p1": ["F332 构图偏右"]
}
```

- `scores` 必须且只能有五个键：`action`（动作）、`pacing`（节奏）、`framing`（构图）、`quality`（画质）、`audio`（声音），每个 0–10。
- `p0`/`p1` 是字符串列表，可为空；每条须带帧号或可核实的位置。P2/P3 不进入评分表，记 `deferred:`。
- `version` 与 `reviewer` 必填。评审者必须是没有参与该版制作的独立代理或人。

## 使用

```bash
$P $T/check.py scorecard docs/reviews/v13/score.json
$P $T/check.py scorecard docs/reviews/v14/score.json --baseline docs/reviews/v13/score.json
```

第一条只校验结构；第二条同时比较总分，低于基线就 FAIL。检查器不判断分数是否真实，只保证维度、范围和基线可比。分数与 P0/P1 必须来自实际看片，不能照抄示例。
