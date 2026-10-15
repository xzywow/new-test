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

### 使用提供的店小秘 2.8.88 CRX 安装包

正式版 Chrome 不提供可靠的本地 CRX 静默安装方式，较新版本还限制 `--load-extension` 启动参数。工具不修改 Chrome 策略、Preferences 或安装记录；新增的是**自动校验和解包，首次人工加载**。已有登录记录和安装状态继续由同一独立 Chrome 保存。

将原始 `dxm_crawl_2.8.88.crx` 放在项目目录，关闭先前启动的独立 Chrome，在 PowerShell 执行：

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe plugin_probe.py --crx ".\dxm_crawl_2.8.88.crx" --extension-id "ioadaikpljilagoddljnamloiebcoopb" --product-url "https://www.aliexpress.com/item/1005012488453051.html"
```

首次启动后，在独立 Chrome 的 `chrome://extensions` 页面打开右上角“开发者模式”，点击“加载已解压的扩展程序”，选择终端打印的完整目录（位于项目 `.local-extensions` 内的校验和目录，不能选择 CRX 文件或其父目录）。核对名称“店小秘助手”、版本 2.8.88、ID 及启用状态，再回终端按 Enter。若安装了相同 ID 的另一个版本，先停止并检查，不自动卸载或覆盖。

如果当前诊断程序仍在等待，可以打开另一个 PowerShell，进入项目目录，仅执行解包：

```powershell
.\.venv\Scripts\python.exe extension_package.py --crx ".\dxm_crawl_2.8.88.crx"
```

随后在已经打开的独立 Chrome 中人工加载打印出的目录，再回原终端继续。此命令只准备文件，不启动或操纵浏览器。

包内为 Manifest V3，公钥推导 ID 与上述 ID 一致。只接受本次提供的原始文件 SHA-256：`d76762adb53085d44f75e53e5b54ff0db769211942521889d30583ca44e6c6ac`。校验用于确保文件与已检查附件相同，**不是官方来源证明，也不是 CRX 签名认证**；官方来源仍需用户核对。工具不更改 manifest 或扩展代码来绕过验证。不同版本或改动后的文件会拒绝；已解包文件若变化也拒绝复用。不要手改校验和来放行未知包。

安装包、解包目录均保留在本机并由 Git 忽略，不随代码发布，因此更新代码不会自动下载插件。此扩展自身申请 cookies、webRequest 等权限，具体权限需在 Chrome 中由用户审阅；本工具不读取凭据。解包加载后的更新、权限及后台行为由 Chrome 和扩展管理，不代表已经验证采集兼容性。保留解包目录，否则后续启动扩展可能无法加载。

### 先打开日常已登录 Google 账号的 Chrome

不再使用独立浏览器时，先在原诊断终端按 Ctrl+C 结束程序，再更新并运行：

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe open_chrome.py --product-url "https://www.aliexpress.com/item/1005012488453051.html"
```

这个入口使用普通 Chrome 自己的现有资料，不创建独立目录、不开启调试端口、不复制凭据。如果有多个 Chrome 资料，由 Chrome 选择已有资料，程序无法保证自动选择已登录的那个；请在右上角头像手动切换。Google 登录不等于店小秘或速卖通已经登录，仍需分别检查。

需要固定资料时，在目标 Chrome 中打开 `chrome://version`，查看“个人资料路径”的末尾目录名（如 `Default` 或 `Profile 1`），只将这个目录名传给 `--profile "Profile 1"`，不要分享完整路径或账号信息。目录名需来自已有资料，否则 Chrome 可能新建该资料。

此入口只打开浏览器和商品页，不附着 Playwright，不自动安装插件，也不验证采集结果。请通过已安装的官方插件手动测试一个商品，再到采集箱按来源 ID 核对。真实 Chrome 打开及登录状态尚需 Windows 本机验证。

## JOOM 商品字段与本地导入文件准备

已按提供模板加入 12 项个人必填校验、日期序号 SKU 的 SQLite 持久化分配以及保留原模板的本地导出。规则、单位、定价和运行方式见 [PRODUCT_WORKFLOW.md](PRODUCT_WORKFLOW.md)。该功能不会向店小秘导入或发布；售价和搜索标签没有对应模板列，需要单独适配。

## 试验：操作当前已登录 Chrome 的一个商品

新增 `desktop_collect.py`：Windows UI Automation 读取实际窗口/地址栏/控件树，定位唯一“开始采集”按钮，按控件实时区域点击一次，等待“采集成功”，再从店小秘可见来源字段核对商品 ID。**这是待 Windows 本机验证的试验功能，模拟测试不代表真实 Chrome 已兼容。** 没有使用固定坐标、剪贴板、CDP 或隐藏接口；不保存截图、网页正文或登录凭据。

先确认店小秘采集箱中尚不存在目标商品；已有商品只运行 `--verify-only`。首次测试请使用另一个尚未采集的商品；此前 `1005012488453051` 已人工采集，不能再次用它测试点击。

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
.\.venv\Scripts\python.exe desktop_collect.py --product-url "https://www.aliexpress.com/item/替换为尚未采集的数字ID.html"
```

程序不会打开或切换浏览器，先手动打开已登录的 Chrome 目标商品页。终端输入 `COLLECT` 后，有 5 秒切换回正确 Chrome 标签页；之后不要操作鼠标键盘。必须能通过 UIA 读到前台 Chrome 地址栏、浮窗标识及唯一按钮，并通过实时元素命中检查后才点击。地址栏不识别、按钮不是可访问控件、被遮挡、验证码、旧成功提示、未知子窗口、焦点改变或超时都会停止，绝不猜坐标或自动再次点击。如果你电脑 Chrome 的可访问性不支持这些控件，本版本不可用，需要进一步本机适配，不能据此声称按钮已点击。

读取成功提示后，**仍需你手动进入店小秘采集箱、搜索来源 ID 并打开该商品详情页**。回终端按 Enter，再在 5 秒内切回该详情页，程序读取可见“来源URL”及精确商品 ID。此版本没有自动导航店小秘后台，因此整条链路是半自动，不能宣称全自动。不会点击保存、认领、编辑字段或发布。

未知结果或已有商品只核验：

```powershell
.\.venv\Scripts\python.exe desktop_collect.py --verify-only --product-url "https://www.aliexpress.com/item/1005012488453051.html"
```

每个商品的尝试在点击前写入本地 `output/desktop-attempts.sqlite3`，即使中断、点击前检查失败或崩溃，后续也拒绝自动重复点击。先人工核验，不要删库强行重试。标记 `verified_present` 只证明当前店小秘可见来源匹配，不保证是此次新建，也不保证历史未重复。此功能一次只处理一个商品、不并发，SQLite 文件需要保留。

Ctrl+C 可在终端中断，操作系统可切走 Chrome 让后续检查停止；这不是全局紧急停止键，已发出的点击无法撤回。保持 Windows 解锁，终端与 Chrome 以同等权限运行（推荐均普通权限），不要在锁屏或远程会话断开时运行。

### 跳过采集箱来源核验及窗口诊断

按当前用户要求，可在命令末尾增加 `--skip-source-verification`，程序读取插件“采集成功”提示后结束，不要求进入采集箱。任务保存为 `plugin_success_unverified`，不是已核验成功，后续也不会自动再次点击。不能与 `--verify-only` 同用；仍保留前台 Chrome、地址栏、目标商品和按钮检查。

```powershell
.\.venv\Scripts\python.exe desktop_collect.py --product-url "https://www.aliexpress.com/item/替换为新商品ID.html" --skip-source-verification
```

确认词兼容 `COLLECT` 和 `collect`。窗口切换时间现默认为 10 秒，可用 `--switch-seconds 15` 调整。此前文档中的 5 秒说明对应旧版。

若提示无法读取地址栏，先运行只读诊断（不点击、不写任务）：

```powershell
.\.venv\Scripts\python.exe desktop_collect.py --diagnose
```

执行后在 10 秒内切到目标 Chrome 页面。输出只含控件数量、类型、是否识别地址栏及网站类别，不包含地址、账号或表单内容。可以把终端输出发来继续适配。新版支持浏览器原生工具栏内的 Edit/ComboBox 地址栏定位，拒绝网页模仿的地址输入框。若仍无法识别，不跳过安全检查或猜坐标点击。推荐终端与 Chrome 均以普通用户权限运行。

### 最新启动方式：5 秒后直接执行

按用户当前要求，默认窗口切换时间恢复为 5 秒，采集命令不再询问 `COLLECT`。显式 `--switch-seconds` 仍可覆盖。请先打开并加载目标商品页，再执行 `desktop_collect.py --product-url "实际商品链接" --skip-source-verification`，5 秒内切回 Chrome。运行命令即开始一次采集尝试；保留地址栏、按钮、焦点、防重复和异常停止检查。此前关于默认 10 秒和输入 collect 的说明已被此规则替代。非跳过模式仍需人工打开店小秘详情并按 Enter 开始来源核验。

### 旧版“前台不是 Chrome”后记录误锁定修复

新版把写入待核验记录的时机移至地址栏、按钮、焦点和覆盖检查全部通过之后、实际点击之前。因此新版在检查阶段停止不会误记采集尝试；实际点击已尝试或结果未知时仍保留记录、防止重复。

旧版可能在尚未点击时就留下 `pending_verification`。只有明确看到旧运行在“前台不是 Chrome”等点击前检查处停止，并人工确认没有点击/入箱的情况下，才能对该一个商品执行：

```powershell
.\.venv\Scripts\python.exe desktop_collect.py --product-url "https://www.aliexpress.com/item/1005012087206250.html" --clear-confirmed-no-click
```

此命令仅将指定商品记录标记为“人工确认未点击”，不执行采集、不删除其他任务、不放行成功状态。再运行正常采集命令。超时、崩溃、已点击但无成功提示等情况不能用它解除，应先核验。无需删除数据库。执行采集命令后须在 5 秒内 Alt+Tab 切到目标 Chrome 商品页；停留在 PowerShell 会被正确拦截。
