# Brandflow 0.7.x 部署 QA 验收清单

本清单用于在 Windows 部署包（见 `packaging/windows/README.md`）安装完成后，逐项验证系统是否可用。

验收环境：Windows 10/11，项目已解压到目标目录（如 `D:\brandflow`），`tools/bin/` 已放置 `ffmpeg.exe`、`ffprobe.exe`、`whisper-cli.exe`。

---

## 1. 健康检查

### 验证步骤
1. 启动后端（若未启动，运行 `packaging\windows\start.bat`）。
2. 浏览器或 curl 访问 `http://localhost:17890/api/health`。
3. 访问 `http://localhost:17890/api/health?deploy_check=true`。
4. 在终端执行：
   ```cmd
   uv run python -m packages.deploy_health
   ```

### 期望结果
- [ ] 访问 `http://localhost:17890/api/health` 返回版本号 `0.7.x`
- [ ] 访问 `http://localhost:17890/api/health?deploy_check=true` 所有检查项通过
- [ ] 部署体检 CLI `uv run python -m packages.deploy_health` 输出 overall pass

### 失败时的下一步
- 检查 `logs/backend.log` 是否有启动错误。
- 确认端口 `17890` 未被占用。
- 若体检报工具缺失，按提示将对应 `.exe` 放入 `tools/bin/` 或设置环境变量 `FFMPEG_PATH` / `FFPROBE_PATH` / `WHISPER_CLI_PATH`。

---

## 2. 前端首页

### 验证步骤
1. 确认前端开发服务器已启动（`packaging\windows\start.bat` 会同时启动）。
2. 浏览器访问 `http://localhost:5173`。
3. 查看页面顶部导航栏，确认产品选择器存在。
4. 点击产品选择器，切换不同产品。

### 期望结果
- [ ] 访问 `http://localhost:5173` 页面正常加载
- [ ] 导航栏显示产品选择器和工作正常

### 失败时的下一步
- 查看 `logs/frontend.log` 是否有启动报错或端口冲突。
- 确认 `frontend/node_modules` 已安装。
- 若端口 `5173` 被占用，关闭占用进程或修改前端启动端口。

---

## 3. 产品配置

### 验证步骤
1. 访问 `http://localhost:5173/system/config/product`。
2. 检查产品列表是否显示已有产品。
3. 点击“新建产品”，输入名称后保存。
4. 选择一个产品，点击“重命名”，修改名称后保存。
5. 选择一个产品，点击“删除”，确认对话框出现后确认删除。
6. 选择一个产品，展开产品级分类配置，新增、编辑、删除分类。

### 期望结果
- [ ] 访问 `/system/config/product` 页面正常加载
- [ ] 产品列表显示已有产品
- [ ] 可新建产品
- [ ] 可重命名产品
- [ ] 可删除产品（含确认对话框）
- [ ] 产品级分类配置可正常增删

### 失败时的下一步
- 查看浏览器控制台（F12）是否有接口报错。
- 检查后端日志 `logs/backend.log` 对应产品配置接口的响应。
- 确认 `workspace/` 目录有写入权限。

---

## 4. 素材上传与入库

### 验证步骤
1. 访问 `http://localhost:5173/system/assets`。
2. 使用页面顶部产品筛选器选择指定产品。
3. 点击分类 dropdown，确认下拉项与该产品配置的分类一致。
4. 点击上传按钮，选择一个本地视频素材并上传。
5. 上传完成后，在素材列表查看新素材。
6. 点击素材详情，确认 `product` 字段不为空。
7. 确认缩略图已生成并显示。
8. 切换产品筛选器，确认可按产品筛选素材。

### 期望结果
- [ ] 访问 `/system/assets` 页面正常加载
- [ ] 产品筛选器正常工作
- [ ] 分类 dropdown 显示产品级分类
- [ ] 可上传视频素材
- [ ] 素材入库成功，`product` 字段不为空
- [ ] 素材缩略图正常生成
- [ ] 可按产品筛选素材

### 失败时的下一步
- 检查后端日志 `logs/backend.log` 是否有上传接口异常。
- 确认 `workspace/assets/` 有写入权限。
- 若缩略图未生成，检查 `ffmpeg.exe` 是否可被正常调用。

---

## 5. 缺失工具的失败提示验证

### 验证步骤
1. 先备份 `tools/bin/ffmpeg.exe`，然后临时移除该文件。
2. 尝试上传一个视频素材，记录错误提示。
3. 恢复 `ffmpeg.exe`。
4. 备份并临时移除 `tools/bin/ffprobe.exe`。
5. 再次尝试上传一个视频素材，记录错误提示。
6. 恢复 `ffprobe.exe`。

### 期望结果
- [ ] 临时移除 `ffmpeg.exe`，上传素材应显示可理解错误（非 `[WinError 2]`）
- [ ] 临时移除 `ffprobe.exe`，上传素材应显示可理解错误
- [ ] 错误信息包含缺失工具名称和修复建议

### 失败时的下一步
- 若仍出现 `[WinError 2]` 等系统级报错，检查上传/入库逻辑是否对工具缺失做了明确包装。
- 确认错误文案包含缺失工具名（如“未找到 ffmpeg.exe”）和修复建议（如“请将其放入 tools/bin/ 目录”）。

---

## 6. 日志文件

### 验证步骤
1. 启动服务后，检查项目根目录下 `logs/` 文件夹。
2. 打开 `logs/backend.log` 和 `logs/frontend.log`。
3. 模拟一次启动失败（如占用端口后启动），查看日志是否写入固定路径。

### 期望结果
- [ ] `logs/backend.log` 存在且可读
- [ ] `logs/frontend.log` 存在且可读
- [ ] 启动失败时日志路径固定且容易定位

### 失败时的下一步
- 确认 `start.bat` 是否正确重定向了 stdout/stderr 到 `logs/`。
- 若日志不存在，检查目录权限或脚本输出路径配置。
- 启动失败时若日志分散，统一使用 `logs/` 目录作为排查入口。

---

## 7. 重启/重复部署

### 验证步骤
1. 停止当前运行的 `start.bat` 窗口。
2. 重新运行 `packaging\windows\start.bat`，等待启动完成。
3. 再次访问 `http://localhost:17890/api/health` 和 `http://localhost:5173`。
4. 停止服务后，重新运行 `packaging\windows\init.bat`。
5. 检查已有 `.env`、`config/app_config.json`、产品配置、素材数据是否仍然保留。

### 期望结果
- [ ] 停止服务后重新运行 `start.bat`，服务正常启动
- [ ] 重复运行 `init.bat` 不会破坏已有配置

### 失败时的下一步
- 若重启后无法启动，检查端口占用和日志。
- 若 `init.bat` 覆盖了配置，检查脚本逻辑是否跳过已存在的 `.env` 和业务配置文件。

---

## 验收结果

| 检查项 | 结果 | 备注 |
|--------|------|------|
| 1. 健康检查 | 通过 / 未通过 | |
| 2. 前端首页 | 通过 / 未通过 | |
| 3. 产品配置 | 通过 / 未通过 | |
| 4. 素材上传与入库 | 通过 / 未通过 | |
| 5. 缺失工具提示 | 通过 / 未通过 | |
| 6. 日志文件 | 通过 / 未通过 | |
| 7. 重启/重复部署 | 通过 / 未通过 | |

**验收人：** _______________  
**验收日期：** _______________  
**总体结论：** 通过 / 未通过
