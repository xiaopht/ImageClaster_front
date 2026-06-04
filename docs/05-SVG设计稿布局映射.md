# SVG 设计稿到小程序布局映射

本项目的 SVG 设计稿位于 `D:\夏特项目\AI识图-UI分页设计\AI转存SVG格式\AI转存SVG格式`。SVG 画板统一为 `1290 x 2796`，小程序样式按 `750rpx` 宽度实现，因此主要换算比例为：

```text
1 SVG px = 750 / 1290 = 0.5814rpx
```

## 页面对应关系

- `AI识图_UI界面__01-1.svg`：首页默认搜索/上传页面，对应 `miniprogram/pages/index/index.wxml` 与 `index.wxss`。
- `AI识图_UI界面__01-5.svg`：花色大图详情弹层，对应全局 `miniprogram/app.wxss` 中的 `.detail-*`。
- `AI识图_UI界面__02-2.svg`：我的页收藏/浏览记录卡片页，对应 `miniprogram/pages/mine/mine.wxml` 与 `mine.wxss`。
- `AI识图_UI界面__03-1.svg`、`AI识图_UI界面__03-2.svg`：客服对话页，对应 `miniprogram/pages/service/service.wxml` 与 `service.wxss`。

## 已落地的关键尺寸

- 首页上传框：SVG `x=51.91, y=440.39, width=1185.67, height=608.12`，小程序约为左右 `30rpx`、高度 `354rpx`。
- 首页匹配模式面板：SVG `height=365.7`，小程序用 `.mode-panel` 控制内边距和行距。
- 首页开始搜索按钮：SVG `width=662.5, height=149.18`，小程序约为 `56%` 宽、`84rpx` 高。
- 大图详情主图：SVG `x=66.93, y=580.24, width=1156.14, height=1506.3`，小程序为 `calc(100vw - 78rpx)` 宽、`876rpx` 高。
- 大图“更多颜色”：SVG `width=276.09, height=65.72`，小程序为 `160rpx x 38rpx`。
- 我的页双列卡片：SVG 单卡 `width=554.28, height=739.04`，小程序约为两列 `48.5%` 宽、图片高 `360rpx`。
- 客服页头部：SVG `height=322.03`，小程序为 `188rpx`。
- 客服主气泡：SVG `width=822.05`，小程序最大宽约 `478rpx`。
- 客服输入栏：SVG `height=140.89`，小程序为 `82rpx`。

## 功能性差异

以下差异是为了保留已确认的功能要求，而不是视觉稿遗漏：

- 辅助分类比 SVG 多一个“不使用”选项，并默认选中。
- 首页“重置”按钮保留在搜索框右侧，避免被微信开发者工具右上角胶囊按钮遮挡。
- 花色详情左上角保留 `PDF` 按钮。

