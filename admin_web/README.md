# schattdecor Sense 后台网站

这是独立的运维后台，不会显示在小程序页面中。

本地测试地址：`http://127.0.0.1:8000/admin/`。

正式地址规划为：`https://decorsense.schattdecor.cn/admin/`。

主要功能：

- 管理允许登录小程序的员工手机号、姓名和权限。
- 查看并批准或拒绝陌生手机号的登录申请。
- 查看识别事件、反馈、未匹配图片、训练数据和样品单。

手机号和登录申请接口只允许 `admin` 账号访问。生产环境还必须配置 `WECHAT_APP_ID` 与 `WECHAT_APP_SECRET`。
