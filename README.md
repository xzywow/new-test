# 店小秘采集箱只读工具（第一阶段）

Python 3.10+，支持 Windows 本地 Chromium；手动登录后读取当前采集箱列表，去重导出 JSON/Excel。没有编辑、删除、认领或发布功能。

## Windows PowerShell

```powershell
git clone https://github.com/xzywow/new-test.git
cd new-test
git switch main
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe main.py
```

浏览器打开后手动登录，进入采集箱，等待商品加载，再回到终端按 Enter 并选择标签页。默认由用户手动翻页、输入 y 继续读取；重复页会停止，最多读取 100 页，可用 `--max-pages` 修改。结果保存在 `output/时间戳/`；错误写入 `reader.log`，发生异常会以非零状态退出并将已读取商品保存到 `partial/`。

登录状态保存在本机 `.browser-profile/`，包含敏感会话信息，请勿共享或提交。登录阶段允许网站正常请求；开始读取后拦截 POST/PUT/DELETE 等非读取请求。这可能阻止店小秘通过 POST 加载列表或翻页，此时应停止并根据真实网页调整只读接口策略，不能笼统放开请求。不要在浏览器中手动执行商品修改操作；GET 请求及用户操作不能由此工具保证无副作用。

## 页面适配与限制

**尚未连接真实店小秘账号或验证真实页面。** 默认选择器只是可测试的适配起点，不代表已适配生产 DOM。没有识别到商品会报错，不会声称导出成功。读取仅限当前页面可见行；虚拟滚动列表只会导出已渲染行，不支持 iframe 内列表或自动滚动。价格保留页面原始文本，不推断币种、库存或隐藏字段。商品 ID 优先取行属性/明确 ID 单元格，否则取速卖通链接中的 ID。

可创建本地 `selectors.json`，通过开发者工具检查真实页面后填写：

```json
{
  "selectors": {
    "rows": "table tbody tr",
    "title": ".product-title",
    "source": "a[href*=\"aliexpress.com/\"]",
    "price": ".price",
    "id": ".product-id"
  }
}
```

运行 `python main.py --selectors selectors.json`。商品行必须有标题以及商品 ID 或速卖通来源链接。默认只识别 aliexpress.com 及其子域名来源。去重优先使用商品 ID，其次使用去除查询参数的来源 URL。

可选 `next_selector` 支持传统同路径、同源、仅查询参数变化的下一页 `<a href>` 导航；只应填写人工核对的下一页链接选择器。工具不会点击按钮或执行 JavaScript 分页。SPA/POST 分页请使用默认手动翻页，若请求被保护策略阻止需进一步真实页面适配。达到页数上限会记录警告，导出不保证覆盖采集箱所有商品。

## 开发验证

```bash
python -m unittest discover -s tests -v
python -m compileall -q .
```

测试使用本地 HTML 和无头 Chromium 验证可见行解析、分页、去重、导出与请求拦截，不访问真实店小秘。真实账号登录、真实页面选择器以及 Windows 桌面端仍需用户本机验证。不要将测试通过理解为真实商品已采集成功。

云环境验证：安装依赖成功；浏览器下载域名被网络策略阻止，因此实际浏览器测试使用已安装的系统 Chromium，命令为 `PLAYWRIGHT_EXECUTABLE_PATH=/usr/bin/chromium .venv/bin/python -m unittest discover -s tests -v`。如使用已有 Chrome/Chromium，可通过 `PLAYWRIGHT_EXECUTABLE_PATH` 指定可执行文件；Windows 默认使用上面命令安装的 Playwright Chromium。

## 新重点：阶段 A 官方插件可行性诊断

此阶段只验证一个商品；不执行整店采集。详见 [FEASIBILITY.md](FEASIBILITY.md)。原 `main.py` 保留为独立的只读导出工具。

### Windows PowerShell 步骤

1. 安装 Google Chrome 和 Python 3.10+。在仓库运行以下命令更新并安装依赖：

```powershell
git switch main
git pull --ff-only
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. 从店小秘官网指向的官方来源安装/确认扩展。打开 `chrome://extensions`，启用开发者模式以查看扩展 ID，确认启用。不要安装同名未知扩展。
3. 用真实的扩展 ID 和一个尚未采集的速卖通商品 URL 替换下面示例。工具会检测 Chrome，启动独立浏览器；首次需要在这个独立浏览器里重新从官方来源安装扩展，不复制原浏览器个人资料。

```powershell
.\.venv\Scripts\python.exe plugin_probe.py --extension-id "替换为32位扩展ID" --product-url "https://www.aliexpress.com/item/替换为商品数字ID.html"
```

4. 按终端提示手动登录、完成验证、打开目标商品和采集箱。查看插件页面入口/工具栏弹窗，记录是单品还是批量。若有验证码或未知弹窗，停止，不绕过。
5. 在采集箱按目标来源 ID 搜索，先读基线。已有商品会跳过。确认后只通过官方插件手动采集一个商品，再手动刷新/搜索采集箱，由程序核对来源链接 ID。无唯一来源链接会保持待核验。若真实商品行不是表格，用 `--rows "实际商品行CSS选择器"` 指定，确保选中单条商品容器而非整页。
6. 查看 `output/plugin-probe.json`。只有真实核验后才能讨论进一步自动化。可随时 Ctrl+C 停止；浏览器由你手动关闭。不要在未知结果下直接重试采集。

### 复用已授权 Chrome

优先支持 `--endpoint http://127.0.0.1:端口` 连接用户明确授权的调试浏览器，不自动扫描调试端口，不连接远程机器。Chrome 136+ 通常不允许在默认个人数据目录启用远程调试；普通正在运行的 Chrome 无法可靠直接接管。不要复制其资料或强制关闭个人 Chrome。默认独立目录是更可靠的退路。

如果你已经手动启动了一个独立目录 Chrome 调试实例，可使用：

```powershell
.\.venv\Scripts\python.exe plugin_probe.py --endpoint "http://127.0.0.1:9223" --extension-id "替换为32位扩展ID" --product-url "https://www.aliexpress.com/item/替换为商品数字ID.html"
```

调试端口拥有较高浏览器访问权限，只绑定本机，使用后关闭浏览器，不要暴露给网络。不记录 endpoint、页面 URL 列表、网页内容或凭据。默认报告只保存商品 URL 的规范化形式，去掉查询串。截图未自动采集，避免意外包含账号信息。独立浏览器文件位于 `.diagnostic-chrome/`，不提交 Git。

### 测试范围

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

测试包含模拟 Windows Chrome 检测、扩展清单元数据、CDP 地址限制和本地 HTML 核验。不包含真实 Windows 桌面、官方扩展、真实账号或采集操作；不得把测试通过解释为已采集真实商品。
