# 测试验收证据 (Test Evidence)

- **Commit**: `4d4f67e` (branch: `feat/smart-workflow`)
- **命令 1**: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`
  - **结果**:
    ```
    test_accepts_legacy_manual_events (test_remake_gate.TestRemakeApprovalGate.test_accepts_legacy_manual_events) ... ok
    test_rejects_tampered_approval (test_remake_gate.TestRemakeApprovalGate.test_rejects_tampered_approval) ... ok
    test_rejects_unapproved_render (test_remake_gate.TestRemakeApprovalGate.test_rejects_unapproved_render) ... ok
    test_imports_exist (test_smart_approval.TestSmartApprovalRed.test_imports_exist) ... ok
    test_imports_exist (test_smart_index.TestSmartIndexRed.test_imports_exist) ... ok
    test_imports_exist (test_smart_match.TestSmartMatchRed.test_imports_exist) ... ok
    test_does_not_mutate_source (test_smart_schema.TestSmartSchemaRed.test_does_not_mutate_source) ... ok
    test_fingerprint_deterministic (test_smart_schema.TestSmartSchemaRed.test_fingerprint_deterministic) ... ok
    test_imports_exist (test_smart_schema.TestSmartSchemaRed.test_imports_exist) ... ok
    test_rejects_changed_reference_boundaries (test_smart_schema.TestSmartSchemaRed.test_rejects_changed_reference_boundaries) ... ok
    test_rejects_unknown_schema (test_smart_schema.TestSmartSchemaRed.test_rejects_unknown_schema) ... ok

    Ran 11 tests in 0.001s
    OK
    ```
- **命令 2**: `D:/2/dev/claude-video/.venv/Scripts/python -X utf8 D:/2/dev/yanyun-cut/tools/check_revideo.py --fast`
  - **结果**:
    ```
    PASS 维护源与部署脚本逐字节一致
    Ran 16 tests in 1.552s (ReferenceReviewTests) OK
    Ran 12 tests in 39.287s (MediaTests) OK
    selftest ok
    PASS_SCORECARD 评分表有效
    PASS 部署副本一致性
    PASS 参考复核测试
    PASS 媒体测试
    ```


## Work Record - 2026-11-12T17:18:10+02:00
- Commit SHA: `4d4f67ef83da2030a3a3c87815c1aebd3ccb6b4d`
- Evidence File: `D:\2\dev\revideo\handoffs\revideo-smart-workflow\TEST_RESULTS.json`
- Command: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`
- Exit Code: `0`
- Executed At: `2026-11-12T17:17:00Z`
- Evidence Hash: `e0a66fae2be20b557fe2100138b9bc9d10e01ec6e1d4d4ebd110b90eae22385e`
- Summary: 在 feat/smart-workflow 分支完成 M0-M3 模块落地，测试全量通过
- Test Evidence Content:
```
{
  "tested_sha": "4d4f67ef83da2030a3a3c87815c1aebd3ccb6b4d",
  "command": "python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v",
  "exit_code": 0,
  "timestamp": "2026-11-12T17:17:00Z",
  "stdout": "Ran 11 tests in 0.001s OK"
}
```


## Work Record - 2026-11-12T17:59:51+02:00
- Commit SHA: `482e1adb80ce41b8b4bdda9bdf4fbc567006d21a`
- Evidence File: `D:\2\dev\revideo\handoffs\revideo-smart-workflow\TEST_RESULTS.json`
- Command: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`
- Exit Code: `0`
- Executed At: `2026-11-12T17:58:20Z`
- Evidence Hash: `aeb19693c4bda5d3432f0441d3de3c60b63f555e8abc4068d96f483097af9c99`
- Summary: 已解决 F-001~F-007：修复审批绕过、落地真实 ffmpeg 解码特征抽取、实现 smart_timeline 自主时间轴生成器与 smart_compose 确定性波束搜索，测试 100% 通过
- Test Evidence Content:
```
{
  "tested_sha": "482e1adb80ce41b8b4bdda9bdf4fbc567006d21a",
  "command": "python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v",
  "exit_code": 0,
  "timestamp": "2026-11-12T17:58:20Z",
  "stdout": "Ran 13 tests in 0.003s OK"
}
```


## Work Record - 2026-11-12T18:37:25+02:00
- Commit SHA: `676ca349dd36a0bb76814df639c168e4a955c535`
- Evidence File: `D:\2\dev\revideo\handoffs\revideo-smart-workflow\TEST_RESULTS.json`
- Command: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v`
- Exit Code: `0`
- Executed At: `2026-11-12T18:35:00Z`
- Evidence Hash: `92beb387873c0a4648c1c7450ac37a840912d0998cfdbcf3a21952f8031b2228`
- Summary: 已落实 F-002 至 F-007 全套审查要求：增加 validate_decisions 严格决策核验契约，重构 approve 校验源事件表与决策一致性；素材索引采用真实 ffmpeg 解码与逐帧灰度/动量/动向计算；组接引擎升级为真正波束搜索（beam_width=8）；草稿预览实现低清拼接与 Base64 视频内嵌；原创时间轴正确区分无声与 BGM 模式；remake 支持无音轨渲染；全套 36 项测试 100% 通过（含复刻模式与原创模式 E2E 测试）。
- Test Evidence Content:
```
{
  "tested_sha": "676ca349dd36a0bb76814df639c168e4a955c535",
  "command": "python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v",
  "exit_code": 0,
  "timestamp": "2026-11-12T18:35:00Z",
  "stdout": "Ran 36 tests in 53.919s. OK. 100% pass across approval gate, real video sampling, beam search, draft preview, original timeline, and E2E regression."
}
```


## Work Record - 2026-11-12T18:52:56+02:00
- Commit SHA: `c039a381a7ae189e665ce96754ec120b0b058db3`
- Evidence File: `handoffs\revideo-smart-workflow\TEST_RESULTS.json`
- Command: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast`
- Exit Code: `0`
- Executed At: `2026-11-12T18:51:00Z`
- Evidence Hash: `c5114808b4abd46b34f1d75878f286d42bd549ae4f937ff5c0ec9a3243657881`
- Summary: Addressed F-002 through F-008: mandatory hashes, physical asset hash check, local window features, beam alternatives, original mode gate, and preview compression
- Test Evidence Content:
```
{
  "command": "python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast",
  "tested_sha": "c039a381a7ae189e665ce96754ec120b0b058db3",
  "summary": "37 unit tests and 28 media tests passed (100% OK)",
  "exit_code": 0,
  "unit_tests_passed": 37,
  "media_tests_passed": 28,
  "timestamp": "2026-11-12T18:51:00Z"
}
```


## Work Record - 2026-11-12T19:55:18+02:00
- Commit SHA: `815611570d7749e3ed11f84833c791cf02f24a66`
- Evidence File: `handoffs\revideo-smart-workflow\TEST_RESULTS.json`
- Command: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast`
- Exit Code: `0`
- Executed At: `2026-11-12T19:54:00Z`
- Evidence Hash: `759e65560cea231ce65e77eb9310d1eafc546af915ea71ac4a4a1e76e0a858b1`
- Summary: Addressed F-009: persistent sampled frames in index.json and local window caching verified with regression test
- Test Evidence Content:
```
{
  "command": "python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast",
  "tested_sha": "815611570d7749e3ed11f84833c791cf02f24a66",
  "summary": "38 unit tests and 28 media tests passed (100% OK)",
  "exit_code": 0,
  "unit_tests_passed": 38,
  "media_tests_passed": 28,
  "timestamp": "2026-11-12T19:54:00Z"
}
```


## Work Record - 2026-11-12T20:30:20+02:00
- Commit SHA: `9af9d31c992864497ea43929c9cc552c69dda6a7`
- Evidence File: `handoffs\revideo-smart-workflow\TEST_RESULTS.json`
- Command: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast`
- Exit Code: `0`
- Executed At: `2026-11-12T20:29:00Z`
- Evidence Hash: `f3192dc0c5e99fdcb1aac42fa36d69d2f6304158a558859e6a9fbd543418189f`
- Summary: 已完成第7轮代码优化：在 scripts/smart_match.py 增加窗口特征全局缓存 _WINDOW_FEATURE_CACHE 与 clear_window_feature_cache，并在 enumerate_windows 与 score_candidate 中统一规范化 motion_direction 与 dominant_direction，补充 test_window_feature_cache_and_direction_schema 回归单测，全量 39 项单测与 28 项媒体回归全部通过。
- Test Evidence Content:
```
{
  "command": "python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast",
  "tested_sha": "9af9d31c992864497ea43929c9cc552c69dda6a7",
  "summary": "39 unit tests and 28 media tests passed (100% OK)",
  "exit_code": 0,
  "unit_tests_passed": 39,
  "media_tests_passed": 28,
  "timestamp": "2026-11-12T20:29:00Z"
}
```


## Work Record - 2026-11-12T20:46:51+02:00
- Commit SHA: `b4d4d64ca7074c0c7618ab1217f63d9bf966f40e`
- Evidence File: `handoffs\revideo-smart-workflow\TEST_RESULTS.json`
- Command: `python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast`
- Exit Code: `0`
- Executed At: `2026-11-12T20:29:00Z`
- Evidence Hash: `2751859bc4f878d4b50645540e5df05b9a1c774869a59c0070d78fbe138acaca`
- Summary: 全面修复F-011与F-012：重塑窗口缓存键防碰撞机制（明确素材身份、采样帧指纹与算法版本v2），新增双素材空指纹隔离与重采样失效单测；将 check_revideo.py 与媒体回归套件纳入版本化 tools/ 目录，更新 TEST_RESULTS.json，全量 39 项单测与 28 项媒体回归 100% 通过。
- Test Evidence Content:
```
{
  "command": "python -X utf8 -m unittest discover -s tests -p 'test_*.py' -v && python -X utf8 tools/check_revideo.py --fast",
  "tested_sha": "b4d4d64ca7074c0c7618ab1217f63d9bf966f40e",
  "summary": "39 unit tests and 28 media tests passed (100% OK)",
  "exit_code": 0,
  "unit_tests_passed": 39,
  "media_tests_passed": 28,
  "timestamp": "2026-11-12T20:29:00Z"
}
```
