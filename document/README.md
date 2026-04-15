# 欢迎使用 Markdown 文档阅读器

这是默认的欢迎文档，你可以将自己的 `.md` 文件放入 `document/` 目录，重启后即可在左侧目录树中看到。

---

## 功能介绍

| 功能 | 说明 |
|------|------|
| 密码保护 | 启动时读取 `config.json`，自动哈希存储，明文不落盘 |
| 文件树 | 左侧递归展示 `document/` 目录，支持子目录折叠 |
| 全文搜索 | 输入关键词实时检索文档内容，返回匹配预览 |
| Markdown 渲染 | 支持表格、围栏代码块、脚注、定义列表等 GFM 扩展 |
| 语法高亮 | 基于 Pygments，完全离线可用 |
| 文档目录 | 点击「目录」Tab 自动生成标题结构，点击跳转 |
| 代码复制 | 鼠标悬停代码块显示「复制」按钮 |

---

## 修改密码

编辑项目根目录下的 `config.json`：

```json
{
  "password": "你的新密码",
  "port": 5000,
  "docs_dir": "./document"
}
```

重启应用后，密码字段会被自动替换为哈希值，明文不会保留。

---

## 快速开始

```bash
# 开发模式运行
uv run python app.py

# 打包为独立可执行文件
uv run python build.py
```

打包后，`dist/` 目录包含：

```
dist/
├── doc-reader          # 可执行文件（Windows 为 .exe）
├── config.json         # 配置文件，可直接编辑
└── document/           # Markdown 文档目录
```
