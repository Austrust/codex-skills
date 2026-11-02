# 知识库定位、配置与初始化

## 解析顺序

1. 本次请求显式路径：直接用；在回复中说明它优先于默认配置，但不改默认配置。
2. 工作区声明：读工作区根或当前目录 `AGENTS.md`、`README.md` 中的知识库位置声明（例如「长期记忆库 = 99-Agent文件/99-memory」）。本次使用声明位置，不自动改默认配置。
3. 本机默认：`python <skill-dir>/scripts/configure_kb.py resolve --json`
   - 返回 0 且 `available=true`：使用该路径；
   - 返回 3（未配置）或 4（失效）：进入第 4 步。
4. 询问用户用现有目录还是新建目录。不扫描磁盘猜测；已配置路径失效时报告旧路径并要求确认新位置，不擅自重建空知识库。

## 声明与默认冲突

本次按声明执行，并在回复中报告与默认配置的差异。只有用户明确说「以后默认这里」时才更新配置：

```text
python <skill-dir>/scripts/configure_kb.py set <name> <path> --default
```

## 多知识库

- `resolve --name <name>` 选择命名知识库。
- `show --json` 查看全部配置。
- 写入前若多个候选会导致不同写入位置，先问用户。
- 配置只保存名称与路径，不保存知识内容或凭据。
- 配置位置：`$CODEX_HOME/maintain-knowledge-base/config.json`，可用 `MAINTAIN_KB_CONFIG` 覆盖；未设置 `CODEX_HOME` 时默认 `~/.codex`。

## 新建知识库

```text
python <skill-dir>/scripts/init_kb.py <knowledge-base-root> --name "知识库名称"
```

脚本只创建缺失目录和文件，不覆盖现有内容。初始化后：

1. 按真实需求精简或扩展 `catalog/vocabulary.md`；
2. 在根 `AGENTS.md` 记录库内特有约定（不要复制技能流程）；
3. 先登记少量真实对象和项目，再决定是否新增类型；
4. 运行 `audit_kb.py` 建立干净基线；
5. 用户确认后 `set --default`。

## 路径不可写或不可读

先只读检查目录内容与写入边界，再决定是否登记。路径含空格或中文时保留原样并加引号，不改名迁移；迁移按 `backup-restore.md` 的流程处理。
