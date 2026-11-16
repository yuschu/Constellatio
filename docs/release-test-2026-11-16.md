# 发版测试报告（2026-11-16）

> 范围：`D:\InformationTechnologyStudy\Constellatio` 当前工作区（HEAD `a5af121` + 未提交改动）。
> 结论：**代码、测试、容器、真实页面与导出链路均通过，可作为本机/内网发版基线。**
> 公网发布前仍需处理本文「发布前待确认」中的部署配置与测试范围问题；版本记录已更新到 v2.4.1，并已完成 tag 与 Release 发布。

---

## 1. 测试基线

| 项 | 值 |
|---|---|
| 代码提交 | `a5af121 docs: make README bilingual with English default` |
| 工作区 | 最终提交范围 90 个文件，`+6154 / -471`（含 14 项原有未跟踪产物与本报告） |
| Python | `venv\Scripts\python.exe`，settings `plugin_host.settings` |
| 数据库 | 宿主默认 SQLite；容器 MySQL 8.0 |
| 容器 | `constellatio-web-1`、`constellatio-db-1`、`constellatio-ollama-1` |
| 最终镜像 | `constellatio-web:latest`，`sha256:e9c2d68cab95c5183d5eb7522d7604d1dda629288fc0cf7a069be029af0138b9` |
| 容器启动 | 2026-11-16 22:11:40（本地时间） |

---

## 2. 门禁结果

| 检查 | 结果 |
|---|---|
| 宿主 `manage.py check` | `System check identified no issues (0 silenced)`，exit 0 |
| 容器 `manage.py check` | 0 issues，exit 0 |
| `makemigrations --check --dry-run` | `No changes detected` |
| 全量测试 | **703 tests，136.604s，OK，exit 0** |
| 结构插件补跑 | **36 tests，58.643s，OK，exit 0** |
| `tools/compile_mo.py --check` | 1 catalog 与 `.po` 一致，exit 0 |
| 宿主 `pip check` | `No broken requirements found` |
| 容器 `pip check` | `No broken requirements found` |
| JS 静态语法 | 8 个静态 `.js` 全部通过；模板片段渲染后 `node --check` 通过 |
| `docker compose config --quiet` | exit 0 |
| 容器迁移状态 | `showmigrations --plan` pending = 0 |
| 代码 diff whitespace | 修复后 `git diff --check`（排除 docs）exit 0 |

证据：

- 全量日志：`.tmp-test/release-full.log`（末尾 `Ran 703 tests in 136.604s` / `OK`）
- 退出码：`.tmp-test/release-full-exit.txt`（`TEST_EXIT=0`）

---

## 3. 容器与源码一致性

最终镜像已按修复后的源码重建，以下文件宿主与容器 MD5 一致：

| 文件 | MD5 |
|---|---|
| `templates/includes/pagination.html` | `5ec01294a2865cab2d7277e47eb1c9a0` |
| `plugins/blockchain/templates/blockchain/blockchain_list.html` | `8de5cbf893159a7c760363d7ea8cf4a9` |
| `themes/corporate-clean/static/themes/corporate-clean/css/corporate-clean.css` | `f93255535eb7b4393b7bebd8d43c8d34` |
| `plugin_host/exporting.py` | `7f570cc4bc343bdca13dbf82d0ca319c` |
| `plugins/assistant/static/assistant/js/session-menu.js` | `f39aa45267d0888b98bd657c232b842e` |
| `plugins/notice/templates/notice/_panel.html` | `c4e4da1307157eb0fde83f2511660b44` |
| `locale/en/LC_MESSAGES/django.mo` | `015a6489b1b4afecb23773930fd8140c` |
| `plugins/structure/services.py` | `62426e2b2588f4edcbbbcdf16dd014e1` |

容器启动日志确认 `migrate` 无待应用迁移、`collectstatic` 141 个文件、Gunicorn 正常监听 `8000`。

---

## 4. 真实页面与接口

### 4.1 入口可达性

累计抓取 28 个入口：26 个直接 200；2 个浏览器批量 `fetch` 返回 `TypeError: Failed to fetch`，服务端日志均为 `200`，判定为并发/大响应瞬时失败，不是接口失败。

最终镜像重建后复核 11 个关键入口，服务端日志全部 200：

`/`、`/plugins/blockchain/?page=2`、`/plugins/blockchain/1388/`、`/plugins/user/users/?view=new`、`/plugins/user/departments/`、`/plugins/structure/`、`/plugins/workspace/`、`/plugins/approval/`、`/plugins/notice/`、`/plugins/attendance/`、`/plugins/user/profile/`。

补充：`/plugins/assistant/config/` 不存在（404）；正确路由为 `/plugins/assistant/settings/`，浏览器内 200，标题「助手模型配置」。

### 4.2 PDF 导出真实下载

最终镜像上使用容器内临时 admin session + `curl` 实测：

```text
HTTP/1.1 200 OK
Content-Type: application/pdf
Content-Disposition: attachment; filename="activity-records-20261116.pdf"
Content-Length: 214935
```

落盘：`.tmp-test/release-export.pdf`，**214,935 字节**，文件头 `%PDF-`。临时 session 已删除（`deleted=1`）。

浏览器内 `fetch`/XHR 对附件返回 204 空体，属于附件下载语义差异，不是接口失败；服务端日志为 `200 214935`。

### 4.3 关键 UI 几何与行为（1280×800，中文，admin）

| 检查 | 结果 |
|---|---|
| 活动记录分页 | 上一页/下一页 `r-btn r-btn--plain r-btn--sm`，`69.7×28`；第 3 页链接为 `?page=2` / `?page=4` |
| 活动「查看」 | `r-btn r-btn--sm`，`44×28`，保留 `data-ds-panel` |
| 活动详情 | 点击后 URL 到 `/plugins/blockchain/1388/`，列表仍在，原地出现「活动记录 #1388」「通过（未被篡改）」「返回活动记录」 |
| 活动下载菜单 | `aria-expanded=true`，`hidden=false`；CSV / XLSX / PDF 三项指向对应导出接口 |
| 插件开关 | 7 个全部开启；label/input `44×36`、track `36×20`、thumb `16×16` |
| 新建用户「所属部门」 | `select.r-input`，`560×34` |
| 组织架构统计卡 | 前 3 张为 `A.r-card.r-card--link`，指向部门/用户/角色；第 4 张为静态 `DIV.r-card`；侧栏 15 个 SVG、13 个链接 |
| 活动页脚 | 第 3 / 15 页，共 736 条 |

---

## 5. 本轮修复

- `plugins/structure/services.py` 文件末尾多余空行（`209: new blank line at EOF`）已删除，改为 UTF-8 无 BOM、LF、仅保留一个结尾换行。
- `git diff --check -- . ":(exclude)docs/*.md"` 由 exit 2 转为 **exit 0**。
- 因源码变更，已重新执行 `docker compose up -d --build web`，最终容器中该文件 MD5 与宿主一致。

---

## 6. 发布前待确认

### 6.1 部署安全配置

当前容器实际值：

| 项 | 当前值 | 判断 |
|---|---|---|
| `DJANGO_DEBUG` | `0` | 通过 |
| `SECRET_KEY` | 已注入，长度 67 | 通过（未输出具体值） |
| `DJANGO_HTTPS` | `0` | 本机 HTTP 可用；公网需为 `1` |
| `DJANGO_SSL_REDIRECT` | `0` | 本机 HTTP 可用；公网需为 `1` |
| `ALLOWED_HOSTS` | `*` | 公网发布需改为真实域名/主机 |
| `SSO_SHARED_SECRET` | 长度 27，仍是开发默认值 | 若 SSO 对外可达，必须替换为强随机值 |
| 端口绑定 | `0.0.0.0:8000` | 本机/内网可接受；不可信网络建议改为 `127.0.0.1:8000` |

容器内 `manage.py check --deploy` 报 4 个预期 warning：

- `SECURE_HSTS_SECONDS` 未设置
- `SECURE_SSL_REDIRECT` 未开启
- `SESSION_COOKIE_SECURE` 未开启
- `CSRF_COOKIE_SECURE` 未开启

这些与 `DJANGO_HTTPS=0` 的直连 HTTP 模式一致，不是代码缺陷；若公网发布，应通过环境变量开启 HTTPS 后复跑。

### 6.2 版本记录

- 测试时发现：`README.md` 仍写当前基线 `v2.2.15`（2026-11-15，650+ tests）；`docs/release-notes.md` 仍停在 `v2.2.15`（641 项测试）。
- 本次提交前已更新 `README.md`、`docs/release-notes.md`、`docs/roadmap.md` 与 `docs/frontend-refactor-plan.md`，对齐到 **v2.4.1 / 703 项测试**；`v2.4.1` tag 与 Release 已发布（tag `0121265` → `9679c88`，Release 447176845）。
- `requirements.txt` 已加入 `openpyxl==3.1.5` / `reportlab==5.1.0`（v2.4.0 导出注释）。

### 6.3 工作区杂物

未跟踪文件 `0`（134,359 字节，内容为一次 grep 输出）与 `CON`（35 字节，内容为 GitHub 用户名提示）已确认是误生成，不纳入提交，仍原样保留在工作区，待确认来源后清理。

### 6.4 测试范围说明

- 全量 703 项运行在宿主 SQLite 内存测试库。
- 容器 MySQL 只做了 `check`、依赖、迁移状态、真实 HTTP、真实文件下载，**未在容器 MySQL 内重跑全量测试**，避免在生产库实例上创建/销毁 `test_constellatio`。
- 因此 MySQL 专属行为（如特定排序、大小写、索引）不在本次 703 项的直接覆盖范围内；如需更强保证，应在独立测试库上补跑。

### 6.5 发布后 CI 修复

- 发版提交 `9679c88` 与文档提交 `06682a3` 的 CI 均失败：`plugins/attendance/tests.py:980` 的 `f'attendance-records-'` 触发 Ruff `F541`。
- `e1bedfa` 去掉多余 `f` 前缀后 Ruff 通过，但 Django checks 因 CI 只装 `requirements-dev.txt`、缺 `openpyxl` 而失败。
- `9049334` 在 `requirements-dev.txt` 增加 `openpyxl==3.1.5` / `reportlab==5.1.0`；该提交 CI run `43891996423` **success**，Ruff / Django checks / deploy checks / coverage 全部通过。
- `v2.4.1` tag 仍指向 `9679c88`，按“已发布 tag 不回改”不移动；两笔修复只影响测试与 CI 依赖，运行时代码未变。

---

## 7. 发版建议

| 场景 | 结论 |
|---|---|
| 本机 / 可信内网 | **可发版**；版本记录已更新，提交前清理 `0`/`CON`、按需提交当前改动 |
| 公网 / 生产 | **条件通过**；先设置 `ALLOWED_HOSTS`、`DJANGO_HTTPS=1`、`DJANGO_SSL_REDIRECT=1`、替换 `SSO_SHARED_SECRET`，再复跑 `check --deploy` 与 HTTPS 冒烟 |

---

## 8. 证据文件

- `.tmp-test/release-full.log`
- `.tmp-test/release-full-exit.txt`
- `.tmp-test/release-export.pdf`
- `.tmp-test/release-export.headers`
- `.tmp-test/rendered_stats_fetch_fail.js`
