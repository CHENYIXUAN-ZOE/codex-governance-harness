# 0.1.0 受控安装记录

- 日期：2026-07-30
- 目标：`/Users/chenyi/.codex`
- Plugin：`codex-governance-harness@codex-governance-harness-local`
- 源码：`/Users/chenyi/Desktop/Vibe Coding/codex-governance-harness`
- 最终状态：Installed / Healthy

## 安装前基线

- `AGENTS.md`：0 字节。
- `AGENTS.md` SHA-256：`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。
- `config.toml`：7,151 字节。
- `config.toml` SHA-256：`f11217f071009c96fb38ada399c9f52c8d84203a95bce980a02aed113a363462`。
- Harness active state、Plugin 和 marketplace 均不存在。

## 预检

- 20 项自动化测试通过。
- 源码、格式、Plugin、四个 Skill 和 JSON Schema 校验通过。
- 使用真实 `config.toml` 副本的隔离安装、doctor、rollback 循环通过。
- 隔离回退后 `AGENTS.md` 与 `config.toml` 均字节级恢复。
- 事务备份包含 `AGENTS.before` 与 `config.before.toml`。

## 初始真实安装与 canary

初始事务：`20260730T053748Z-ed636ad7`。

- 安装全局 0.1.0 受管区块。
- 通过 Codex CLI 添加本地 marketplace 并安装、启用 Plugin。
- status 与 doctor 无错误、无警告。
- 安装缓存只包含 `.codex-plugin`、`VERSION`、`lib`、`schemas`、`skills` 和 `templates`。
- 5 个全新 ephemeral、read-only canary 全部通过：
  - Lite，无 Skill；
  - Standard，`governed-project-work`；
  - Assured，`governed-project-work` 并暂停；
  - Standard，`initialize-project-harness`；
  - Standard，`audit-governance-harness`。

## 真实 rollback 演练

对初始事务执行 rollback 后：

- `AGENTS.md` SHA-256 恢复为安装前值。
- `config.toml` SHA-256 恢复为安装前值。
- Harness active state、Plugin 和 marketplace 均被移除。
- 其他 9 个已安装 Plugin 的集合保持不变。

## 最终安装

最终事务：`20260730T054043Z-fe9daceb`。

- active state：`installed`。
- Harness Plugin 数量：1。
- Plugin 状态：enabled。
- 安装后 Plugin 总数：10。
- status：`installed`，无错误、无警告。
- doctor：`healthy`，全部检查通过。
- 重新安装后的全新 Standard canary 再次精确通过。
- 最终事务保留 0 字节 `AGENTS.before` 和 7,151 字节 `config.before.toml`。

## 回退入口

安装管理器默认只预览。需要回退时，先运行：

```bash
python3 -B scripts/manage_install.py rollback \
  --codex-home /Users/chenyi/.codex \
  --user-home /Users/chenyi
```

审阅计划后才添加 `--apply`。不要移动源码仓库；本地 marketplace 当前记录其绝对路径。
