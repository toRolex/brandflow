---
name: publish-release
description: Git Flow 发版流程 — 从 develop 创建 release 分支，bump 版本号，写 release notes，PR 合并到 main，打 tag，main 合并回 develop。Use when user says 发版/发布/release/publish/bump version/tag，或要将 develop 的变更发布为正式版本。
---

# Publish Release

按 Git Flow 标准流程发布新版本。

## 前置条件

- develop 分支已包含所有待发布功能
- 用户已确认版本号（默认 +0.0.1）

## 流程

### 1. 确定版本号

```bash
git tag --sort=-version:refname | head -3
```

取最新 tag，按用户要求 bump（默认 patch +0.0.1）。记录新版本号 `vX.Y.Z`。

### 2. 创建 release 分支

```bash
git checkout develop
git checkout -b release/X.Y.Z
```

### 3. Bump 版本号

修改两个文件中的 version 字段：

**`pyproject.toml`** — 第 3 行：

```diff
-version = "旧版本"
+version = "X.Y.Z"
```

**`frontend/package.json`** — 第 4 行：

```diff
-  "version": "旧版本",
+  "version": "X.Y.Z",
```

然后提交：

```bash
git add pyproject.toml frontend/package.json
git commit -m "chore: bump version to X.Y.Z"
```

### 4. 推送并创建 PR 到 main

```bash
git push -u origin release/X.Y.Z
```

使用 `gh pr create --base main`，body 包含 release notes：

```markdown
## Release Notes — vX.Y.Z

### 新功能
- 功能描述

### Bug Fixes
- 修复描述

### 变更的文件
- 文件列表

### 版本
- pyproject.toml: 旧版本 → 新版本
- frontend/package.json: 旧版本 → 新版本
```

### 5. 合并到 main 并打 tag

```bash
gh pr merge <PR_NUMBER> --merge --delete-branch
git checkout main
git pull origin main
git tag vX.Y.Z
git push origin vX.Y.Z
```

### 6. main 合并回 develop

```bash
git checkout develop
git merge main --no-edit
git push origin develop
```

### 7. 验证

```bash
git tag --sort=-version:refname | head -3   # 新 tag 存在
git log main -1 --oneline                    # main 在 tag 上
git log develop -1 --oneline                 # develop 与 main 同步
gh pr view <PR_NUMBER> --json state          # MERGED
```

## 注意事项

- **版本号来源**：git tag 是版本真相，pyproject.toml / package.json 是同步副本
- **不要跳过 main→develop 合并**：否则下次发版会丢失版本号 bump
- **release notes** 从 `git log <上一个tag>..develop --oneline` 提取变更
- **release 分支生命周期**：创建 → bump → PR → 合并后自动删除，不留残余
