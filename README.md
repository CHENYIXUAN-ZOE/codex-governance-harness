# Codex Governance Harness

这是个人 Codex 全局治理 Harness 的唯一维护源。

它采用两层结构：

- 全局 Harness：提供跨项目的最小不变量、风险路由和默认工作方式。
- 项目级 Harness：保存项目自己的事实来源、约束、流程和完成标准。

当前状态：`0.1.0` 已完成源码、项目工具、行为评测和受控全局安装，进入真实任务观察阶段。

## 使用边界

这个目录是正确的建设位置，也是全局 Harness 的唯一维护源。这里的源码可以复用于不同项目，但“在这里建好”不等于“自动对所有任务生效”。

完整链路是：

```text
本源码仓库
  → 受控安装全局 AGENTS 与治理插件
  → 为具体项目初始化或适配项目级 Harness
```

这种分离让全局版本能够统一维护，同时避免开发中的错误立即影响现有项目。

可安全执行的只读入口：

```bash
python3 -B scripts/check_source.py
python3 -B scripts/run_evals.py
python3 -B scripts/manage_install.py install
```

最后一条命令默认只显示真实 `CODEX_HOME` 的安装状态差异。任何 reinstall、rollback 或 uninstall 仍应先审阅 dry-run，再显式添加 `--apply`。

## 设计目标

- 全局兜底，但不把所有任务变成重型流程。
- 项目定制，但不强迫已有项目迁移到统一目录。
- 规则可验证、可版本化、可回退。
- 随模型能力演进，通过评测删除不再需要的脚手架。
- 控制上下文、时间与 Token 成本。

## 目录

```text
global/       将来部署到全局 AGENTS.md 的治理内核源文件
plugin/       精简的可安装运行包：manifest、Skills、schema、模板与共享库
docs/         架构、决策、风险、路线图和当前状态
evals/        代表性路由案例、输出契约和版本化结果摘要
scripts/      源码检查、评测与安装生命周期工具
tests/        隔离临时目录中的确定性工具测试
.agents/      供隔离测试和后续受控安装使用的本地 marketplace
```

## 安全策略

源码建设、全局安装和项目初始化是三个独立阶段。任何安装动作都必须先经过：

1. 源码结构与内容校验。
2. 隔离环境测试。
3. 安装 dry-run 与差异预览。
4. 用户审阅。
5. 备份、受控安装、新任务验证和回退演练。

路线图见 `docs/ROADMAP.md`。
