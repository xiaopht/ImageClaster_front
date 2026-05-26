# schattdecor Sense 本地后台演示页

这个目录是独立后台数据网站，不会打包进小程序页面。

本地测试方式：

1. 在发布包根目录运行 `python server.py` 启动本地演示服务。
2. 打开 `http://127.0.0.1:8000/admin-web/`。
3. 输入测试账号登录并查看本次进程中产生的事件与反馈。该演示后端不提供生产级身份校验或数据持久化。

它读取这些后端接口：`/api/admin/summary`、`/api/admin/events`、`/api/admin/feedback`、`/api/admin/unmatched`、`/api/admin/training-data`、`/api/admin/sample-orders`。
