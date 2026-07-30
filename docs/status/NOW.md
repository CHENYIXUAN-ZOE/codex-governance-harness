# 当前状态

## 当前阶段

阶段 4 已完成；当前为阶段 5：真实任务观察与证据驱动演进。

## 已完成

- 完成现有全局环境的只读基线审计。
- 初始化 Git 仓库。
- 初始化插件 manifest。
- 初始化四个聚焦 Skill。
- 建立全局治理内核草案、架构、ADR、风险登记和路线图。
- Plugin 和四个 Skill 均通过官方校验器。
- 占位符、相对引用、JSON/YAML 和文件重量检查通过。
- 建立版本化 `.harness/project.json` schema 和无第三方运行依赖的契约验证器。
- 实现默认 dry-run、无覆盖、幂等且失败可回滚的项目初始化工具。
- 实现只读项目 Harness 审计和源码结构检查。
- 12 项隔离测试覆盖 Lite、Standard、Assured、已有项目、路径安全、冲突与故障回滚。
- 将维护仓库与精简可安装 Plugin 包分离。
- 实现默认 dry-run 的安装、状态、doctor、rollback 和 uninstall 生命周期。
- 使用真实 Codex CLI 在隔离 `HOME` 与 `CODEX_HOME` 完成安装和回退演练。
- 建立 12 案例行为评测；Treatment 两轮均 12/12 完全正确。
- 建立上下文门禁：全局规则 3,091 字节，平均输入增量 1,413 tokens。
- 当前全套 20 项自动化测试通过。
- 为每次真实安装同时备份原始 `AGENTS.md` 与 `config.toml`。
- 完成真实全局安装、5 项新任务 canary 和真实 rollback 演练。
- rollback 后两个全局文件字节级恢复，其他 9 个 Plugin 不受影响。
- 通过最终事务 `20260730T054043Z-fe9daceb` 重新安装并通过 doctor。

## 尚未完成

- 在不同真实项目类型中的长期摩擦观察。
- 基于真实证据的首次保留、简化或删除决策。

## 当前安全状态

- `~/.codex/AGENTS.md` 已安装唯一的 0.1.0 受管区块。
- `config.toml` 由 Codex CLI 添加本地 marketplace 与启用状态，未被安装器直接编辑。
- `codex-governance-harness@codex-governance-harness-local` 已安装并启用。
- active state、原始 `AGENTS.md` 和原始 `config.toml` 备份均存在。
- 最终 status 与 doctor 健康。

## 下一门禁

在真实任务中记录误触发、漏触发、额外干预、上下文成本和恢复问题；没有重复证据时不增加全局规则。
