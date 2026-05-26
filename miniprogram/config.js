// 默认语言：影响首次进入小程序、无用户语言偏好时的界面文案。
const DEFAULT_LANGUAGE = 'zh-CN';

// 语言切换顺序：影响“EN / 中文”按钮在多语言之间的循环方式。
const LANGUAGE_ORDER = ['zh-CN', 'en-US'];

// 默认全局状态：影响 app.js 启动时写入 globalData 的基础值。
const DEFAULT_APP_STATE = {
  apiBase: 'http://127.0.0.1:8000',
  token: '',
  user: null,
  language: DEFAULT_LANGUAGE,
  fontLoaded: false
};

// 本地缓存键名：影响登录态、语言、接口地址和开发 openid 的读取与写入。
const STORAGE_KEYS = {
  apiBase: 'apiBase',
  token: 'token',
  user: 'user',
  language: 'language',
  devOpenid: 'devOpenid'
};

// 字体配置：影响全局自定义字体加载地址和字体族名称。
const FONT_CONFIG = {
  family: 'HarmonyOS Sans SC',
  regularPath: '/fonts/HarmonyOS_Sans_SC_Regular.ttf',
  faces: [
    { weight: '400', path: '/fonts/HarmonyOS_Sans_SC_Regular.ttf' },
    { weight: '500', path: '/fonts/HarmonyOS_Sans_SC_Medium.ttf' },
    { weight: '700', path: '/fonts/HarmonyOS_Sans_SC_Bold.ttf' },
    { weight: '900', path: '/fonts/HarmonyOS_Sans_SC_Black.ttf' }
  ]
};

// 品牌配置：影响首页、拍摄页、我的页顶部品牌展示。
const BRAND = {
  main: 'schattdecor',
  products: {
    sense: 'Sense',
    vision: 'Vision'
  }
};

// 页面图标字符：影响 WXML 中按钮、收藏、弹窗关闭和切换按钮的显示符号。
const UI_SYMBOLS = {
  reset: '↻',
  search: '⌕',
  camera: '▣',
  startArrow: '↱',
  favorite: '★',
  service: '☏',
  close: '×',
  previous: '‹',
  next: '›',
  profileAvatar: '●'
};

// 通用界面文本配置：影响详情页序号空状态等非业务文案。
const UI_TEXT = {
  emptyDetailCount: '0/0'
};

// Toast 图标配置：影响 wx.showToast 的 icon 值。
const TOAST_ICONS = {
  none: 'none'
};

// 请求方法配置：影响所有 wx.request 的 method。
const REQUEST_METHODS = {
  get: 'GET',
  post: 'POST',
  delete: 'DELETE'
};

// HTTP 状态范围：影响请求成功与失败的判断边界。
const HTTP_STATUS = {
  successMin: 200,
  successMax: 300
};

// 鉴权配置：影响 token 请求头、访客角色、开发 openid 和注册密码规则。
const AUTH_CONFIG = {
  tokenScheme: 'Bearer',
  devOpenidPrefix: 'dev_',
  randomRadix: 16,
  randomSliceStart: 2,
  passwordMinLength: 6
};

// 用户角色配置：影响登录注册、访客态判断和角色展示。
const USER_ROLES = {
  visitor: 'visitor',
  sales: 'sales',
  admin: 'admin'
};

// 授权弹窗模式：影响我的页登录/注册弹窗切换。
const AUTH_MODES = {
  login: 'login',
  register: 'register'
};

// 用户名前缀配置：影响微信临时访客账号的识别。
const USERNAME_PREFIXES = {
  wechatVisitor: 'wx_'
};

// 匹配模式配置：影响首页和拍摄页选择自动检测或全图匹配。
const MATCH_MODES = {
  auto: 'auto',
  full: 'full'
};

// 搜索配置：影响图片识别结果截取、文本搜索数量和浏览记录数量。
const SEARCH_CONFIG = {
  imageResultLimit: 10,
  textResultLimit: 5,
  historyLimit: 30,
  textSearchMode: MATCH_MODES.auto
};

// 媒体选择配置：影响上传图片时可选数量、媒体类型和来源。
const MEDIA_CONFIG = {
  imageCount: 1,
  mediaTypes: ['image'],
  indexSourceTypes: ['album', 'camera'],
  cameraSourceTypes: ['camera', 'album']
};

// 上传配置：影响识别接口上传字段名和裁剪开关传值。
const UPLOAD_CONFIG = {
  fileFieldName: 'file',
  cropFieldName: 'use_crop',
  categoryFieldName: 'category',
  cropEnabledValue: 'true',
  cropDisabledValue: 'false'
};

// 文件类型配置：影响 PDF 下载后的打开方式。
const FILE_TYPES = {
  pdf: 'pdf'
};

// 链接前缀配置：影响远程图片、本地临时图片和 blob 图片的识别方式。
const URL_PREFIXES = {
  http: 'http',
  wxFile: 'wxfile://',
  blob: 'blob:'
};

// 花色默认值：影响后端缺少名称或分类时的兜底展示。
const PATTERN_DEFAULTS = {
  unnamedName: '未命名花色',
  category: '花色'
};

// 错误文案配置：影响内部错误和 HTTP 错误的提示内容。
const ERROR_MESSAGES = {
  httpPrefix: 'HTTP',
  patternRequired: '缺少花色编号'
};

// 未匹配错误码：影响图片识别结果是否展示“数据未匹配”的提示。
const UNMATCHED_ERROR_CODES = ['threshold_not_met', 'confidence_low', 'category_no_match'];

// 事件类型配置：影响用户行为上报到后端的 event_type。
const EVENT_TYPES = {
  moreColors: 'more_colors'
};

// 反馈结论配置：影响识别反馈接口提交的 verdict。
const FEEDBACK_VERDICTS = {
  accurate: 'accurate',
  inaccurate: 'inaccurate'
};

// 线索来源配置：影响销售线索提交时的 project_type。
const LEAD_SOURCES = {
  home: 'home',
  homeResults: 'home_results',
  mine: 'mine'
};

// 我的页标签配置：影响收藏和浏览记录的切换状态。
const MINE_TABS = {
  favorites: 'favorites',
  history: 'history'
};

// 路由配置：影响分享路径和页面跳转路径。
const ROUTES = {
  index: '/pages/index/index',
  camera: '/pages/camera/camera',
  mine: '/pages/mine/mine',
  service: '/pages/service/service'
};

// 表单长度配置：影响反馈备注和线索备注最多可输入的字符数。
const FORM_LIMITS = {
  feedbackNoteMaxLength: 300,
  leadNoteMaxLength: 500
};

// 分类值配置：影响辅助分类选项提交给后端的值。
const CATEGORY_VALUES = {
  empty: '',
  wood: '木纹',
  abstract: '抽象',
  stone: '石纹',
  plain: '素色'
};

// 分类选项配置：影响辅助分类按钮的展示顺序和标签来源。
const CATEGORY_OPTIONS = [
  { labelKey: 'wood', value: CATEGORY_VALUES.wood },
  { labelKey: 'abstract', value: CATEGORY_VALUES.abstract },
  { labelKey: 'stone', value: CATEGORY_VALUES.stone },
  { labelKey: 'plain', value: CATEGORY_VALUES.plain }
];

// 分类识别别名：影响后端返回英文或中文分类时的本地化标签。
const CATEGORY_ALIASES = {
  wood: {
    exact: [CATEGORY_VALUES.wood, 'wood'],
    contains: ['wood']
  },
  abstract: {
    exact: [CATEGORY_VALUES.abstract, 'abstract'],
    contains: []
  },
  stone: {
    exact: [CATEGORY_VALUES.stone, 'stone'],
    contains: ['stone']
  },
  plain: {
    exact: [CATEGORY_VALUES.plain, 'solid', 'plain'],
    contains: []
  }
};

// 分类标签键名：影响 categoryLabel 将分类值映射到哪一个多语言文案。
const CATEGORY_LABEL_KEYS = {
  wood: 'wood',
  abstract: 'abstract',
  stone: 'stone',
  plain: 'plain'
};

// TabBar 文案键名：影响运行时切换中英文后底部导航文字。
const TAB_BAR_LABEL_KEYS = ['homeTab', 'cameraTab', 'mineTab'];

// 数值格式配置：影响匹配度百分比展示。
const NUMBER_FORMAT = {
  percentMultiplier: 100
};

// 接口路径配置：影响所有后端请求地址，改这里即可调整接口入口。
const API_ENDPOINTS = {
  register: '/api/auth/register',
  login: '/api/auth/login',
  wechatLogin: '/api/auth/wechat-login',
  recognize: '/recognize',
  favorites: '/api/favorites',
  events: '/api/events',
  feedback: '/api/feedback',
  leadContact: '/api/leads/contact',
  userPreferences: '/api/user/preferences',
  favoritesPdf: '/api/favorites/export.pdf',

  // 花色搜索接口：影响首页关键词搜索的查询参数。
  patternSearch(query, limit, searchMode, category) {
    const queryPart = `query=${encodeURIComponent(query)}`;
    const limitPart = `limit=${encodeURIComponent(limit)}`;
    const modePart = `search_mode=${encodeURIComponent(searchMode)}`;
    const categoryPart = category ? `&category=${encodeURIComponent(category)}` : '';
    return `/api/patterns?${queryPart}&${limitPart}&${modePart}${categoryPart}`;
  },

  // 花色详情接口：影响浏览记录上报后获取详情的地址。
  patternDetail(patternId) {
    return `/api/patterns/${encodeURIComponent(patternId)}`;
  },

  // 花色图片接口：影响后端仅返回花色编号时的图片补全地址。
  patternImage(patternId) {
    return `/api/patterns/${encodeURIComponent(patternId)}/image`;
  },

  // 单个收藏删除接口：影响取消收藏时的请求地址。
  favoriteItem(patternId) {
    return `/api/favorites/${encodeURIComponent(patternId)}`;
  },

  // 单个花色 PDF 接口：影响详情弹层导出 PDF 的地址。
  patternPdf(patternId) {
    return `/api/patterns/${encodeURIComponent(patternId)}/export.pdf`;
  },

  // 浏览记录接口：影响我的页浏览历史拉取数量。
  history(limit) {
    return `/api/history?limit=${encodeURIComponent(limit)}`;
  }
};

// 多语言字典：影响页面全部可见文案和运行时 TabBar 文案。
const I18N_DICTIONARIES = {
  'zh-CN': {
    reset: '重置',
    searchPlaceholder: '搜索（输入编号如“57204”或名称如“Amalfi”）',
    uploadChange: '点击可更换图片',
    cropImage: '图片裁剪',
    foldImage: '▼ 折叠图片',
    expandImage: '▶ 展开图片',
    uploadTitle: '点击、拖拽或拍摄上传图片',
    uploadSub: '支持 JPG、PNG、WEBP 格式',
    auxCategory: '辅助分类匹配',
    noAux: '不使用辅助',
    wood: '木纹',
    abstract: '抽象',
    stone: '石纹',
    plain: '素色',
    matchMode: '匹配区域模式',
    autoDetect: '自动检测',
    autoDetectDesc: '（智能识别主体区域）',
    fullImage: '使用全图',
    fullImageDesc: '（使用完整图片）',
    startSearch: '开始搜索',
    matching: '正在匹配花色...',
    searching: '正在搜索...',
    chooseImageOrKeyword: '请选择图片或输入关键词',
    noHighConfidence: '未找到高置信度结果',
    dataUnmatchedTitle: '数据未匹配!',
    dataUnmatchedAdvice: '数据未匹配，请调整拍摄角度，尽量水平或垂直。',
    dataUnmatchedDialogText: '请调整拍摄角度, 尽量水平或垂直。',
    dataUnmatchedConfirm: '确定',
    noTextResults: '未找到相关花色，请试试完整编号、局部编号或其他关键词',
    feedbackPrompt: '这次识别推荐准确吗？',
    feedbackAccurate: '推荐准',
    feedbackWrong: '不准',
    feedbackNotFound: '不准/找不到',
    feedbackDialogTitle: '补充反馈',
    feedbackCorrectPattern: '正确花色编号（可选）',
    feedbackNote: '备注（可选）',
    feedbackCancel: '取消',
    feedbackSubmit: '提交反馈',
    feedbackSatisfaction: '您对匹配结果的满意度',
    feedbackDontRemind: '近期不再提示!',
    feedbackConfirm: '确定',
    feedbackThanks: '感谢反馈',
    leadTitle: '进一步沟通',
    leadIndustry: '行业',
    leadRegion: '地区',
    leadNote: '需求说明 / 联系方式',
    leadSubmit: '提交',
    leadCancel: '取消',
    leadRequired: '请完整填写行业、地区和需求说明/联系方式',
    leadRetry: '提交失败，请稍后重试',
    leadContactTitle: '销售联系方式',
    leadContactName: '联系人',
    leadContactPhone: '电话',
    leadContactEmail: '邮箱',
    leadContactWechat: '微信',
    leadDone: '完成',
    results: '匹配结果',
    foundPrefix: '找到',
    foundSuffix: '条结果',
    customerService: '客服',
    moreColors: '更多颜色',
    matchConfidence: '匹配度',
    exportPdf: '导出 PDF',
    pdfShort: 'PDF',
    favorited: '已收藏',
    demandRecorded: '已记录需求',
    serviceReceived: '客服已收到需求',
    pdfOpened: '已打开 PDF',
    favoriteRemoved: '已取消收藏',
    requestFailed: '请求失败',
    shoot: '拍摄',
    shootUpload: '拍摄或上传图片',
    shootSub: '自动进入花色匹配流程',
    chooseImageFirst: '请先拍摄或上传图片',
    myName: '我的名字',
    guestName: '访客用户',
    roleVisitor: '访客',
    roleSales: 'Sales',
    roleInternal: '内部账号',
    loginRegister: '登录 / 注册',
    switchAccount: '切换账号',
    authLoginTitle: '账号登录',
    authRegisterTitle: '创建账号',
    authLogin: '登录',
    authRegister: '注册',
    authUsername: '用户名',
    authPassword: '密码',
    authAccessCode: '内部访问码（sales）',
    authGoRegister: '没有账号，去注册',
    authGoLogin: '已有账号，去登录',
    authUsernameRequired: '请填写用户名',
    authPasswordRequired: '请填写密码',
    authPasswordTooShort: '密码至少 6 位',
    authLoginSuccess: '登录成功',
    authRegisterSuccess: '注册成功',
    favorites: '我的收藏',
    history: '浏览记录',
    share: '分享 ↗',
    favoritesCountPrefix: '共 ',
    favoritesCountSuffix: ' 个收藏',
    exportFavoritesPdf: '导出收藏 PDF',
    recentPrefix: '最近 ',
    recentSuffix: ' 个花色',
    refresh: '刷新',
    emptyFavorites: '暂无收藏',
    emptyHistory: '暂无浏览记录',
    languageSwitch: 'EN / 中文',
    shareTitle: 'schattdecor Sense',
    favoritesShareTitle: 'schattdecor Sense 收藏夹',
    homeTab: '主页',
    cameraTab: '拍摄',
    mineTab: '我的',
    servicePageTitle: 'AI 客服',
    serviceHideChat: '隐藏聊天窗口',
    serviceDate: '4月14日 星期二 09:00',
    serviceBackTop: '回到顶端',
    serviceWelcome: '您好，我是 AI 客服小夏。为了为您匹配合适的销售服务，需要占用您 1 分钟完成 2 个小问题。您的回答仅用于销售资源精准对接，我们会严格保护您的隐私安全。',
    serviceOccupationPrompt: '请回复您职业的编号，方便我们为您推荐对应领域的销售。',
    serviceOccupationTitle: '您的职业',
    serviceOccupationDesigner: '室内设计师 / 软装设计师',
    serviceOccupationManager: '家装公司项目经理 / 施工负责人',
    serviceOccupationDistributor: '建材 / 饰面材料经销商或代理商',
    serviceOccupationDeveloper: '房地产开发商 / 精装房采购或设计人员',
    serviceOccupationStudent: '建筑或设计相关专业学生 / 教师',
    serviceOccupationOwner: '普通业主 / 自住房装修决策者',
    serviceOccupationBuilder: '工长 / 独立装修师傅',
    serviceOccupationOther: '其他',
    serviceRegionPrompt: '感谢您的反馈。请选择您所在区域，我们将结合区域和职业推送对应销售联系方式。',
    serviceRegionTitle: '所在区域',
    serviceRegionEast: '华东',
    serviceRegionNorth: '华北',
    serviceRegionSouth: '华南',
    serviceRegionSouthwest: '西南',
    serviceRegionOverseas: '海外',
    serviceRegionOther: '其他',
    serviceContactIntro: '感谢您的反馈。根据您的职业与所在区域，对应销售的联系方式为：',
    serviceContactRegion: '对应区域',
    serviceContactName: '销售姓名',
    serviceContactPhone: '手机号',
    serviceContactEmail: '邮箱',
    serviceContactRegionValue: '西南 Southwest China',
    serviceCopyPhone: '仅复制手机号',
    serviceCopyFull: '复制完整信息',
    serviceInputPlaceholder: '输入数字回复...',
    serviceSend: '发送',
    serviceOccupationInvalid: '请回复 1 至 8 中的一个职业编号。',
    serviceRegionInvalid: '请回复 1 至 6 中的一个区域编号。',
    serviceCompleteHint: '联系方式已提供。如需重新匹配，请回复 0。',
    serviceRestarted: '已重新开始匹配，请回复您的职业编号。',
    copied: '已复制'
  },
  'en-US': {
    reset: 'Reset',
    searchPlaceholder: 'Search by decor code, e.g. 57204, or name, e.g. Amalfi',
    uploadChange: 'Tap to replace image',
    cropImage: 'Crop',
    foldImage: '▼ Collapse image',
    expandImage: '▶ Expand image',
    uploadTitle: 'Tap or shoot to upload an image',
    uploadSub: 'JPG, PNG, WEBP supported',
    auxCategory: 'Auxiliary category',
    noAux: 'No auxiliary',
    wood: 'Wood',
    abstract: 'Abstract',
    stone: 'Stone',
    plain: 'Solid',
    matchMode: 'Matching area',
    autoDetect: 'Auto detect',
    autoDetectDesc: '(Detect the main surface)',
    fullImage: 'Full image',
    fullImageDesc: '(Use the complete image)',
    startSearch: 'Search',
    matching: 'Matching decors...',
    searching: 'Searching...',
    chooseImageOrKeyword: 'Choose an image or enter keywords',
    noHighConfidence: 'No high-confidence result found',
    dataUnmatchedTitle: 'No match',
    dataUnmatchedAdvice: 'No data match. Adjust the shooting angle and keep it as horizontal or vertical as possible.',
    dataUnmatchedDialogText: 'Adjust the shooting angle and keep it horizontal or vertical.',
    dataUnmatchedConfirm: 'OK',
    noTextResults: 'No matching decors found. Try a full code, partial code, or another keyword.',
    feedbackPrompt: 'Was this recommendation accurate?',
    feedbackAccurate: 'Accurate',
    feedbackWrong: 'Wrong',
    feedbackNotFound: 'Wrong / not found',
    feedbackDialogTitle: 'Feedback',
    feedbackCorrectPattern: 'Correct decor code (optional)',
    feedbackNote: 'Note (optional)',
    feedbackCancel: 'Cancel',
    feedbackSubmit: 'Submit',
    feedbackSatisfaction: 'How satisfied are you with the match?',
    feedbackDontRemind: 'Do not remind me soon',
    feedbackConfirm: 'OK',
    feedbackThanks: 'Thanks for the feedback',
    leadTitle: 'Further contact',
    leadIndustry: 'Industry',
    leadRegion: 'Region',
    leadNote: 'Need / contact details',
    leadSubmit: 'Submit',
    leadCancel: 'Cancel',
    leadRequired: 'Please fill in industry, region, and need/contact details',
    leadRetry: 'Submit failed. Please try again.',
    leadContactTitle: 'Sales contact',
    leadContactName: 'Name',
    leadContactPhone: 'Phone',
    leadContactEmail: 'Email',
    leadContactWechat: 'WeChat',
    leadDone: 'Done',
    results: 'Results',
    foundPrefix: '',
    foundSuffix: ' results found',
    customerService: 'Service',
    moreColors: 'More colors',
    matchConfidence: 'Match',
    exportPdf: 'Export PDF',
    pdfShort: 'PDF',
    favorited: 'Saved',
    demandRecorded: 'Request recorded',
    serviceReceived: 'Service request sent',
    pdfOpened: 'PDF opened',
    favoriteRemoved: 'Removed',
    requestFailed: 'Request failed',
    shoot: 'Shoot',
    shootUpload: 'Shoot or upload image',
    shootSub: 'Start pattern matching automatically',
    chooseImageFirst: 'Shoot or upload an image first',
    myName: 'My profile',
    guestName: 'Guest',
    roleVisitor: 'Guest',
    roleSales: 'Sales',
    roleInternal: 'Internal',
    loginRegister: 'Sign in / Register',
    switchAccount: 'Switch account',
    authLoginTitle: 'Sign in',
    authRegisterTitle: 'Create account',
    authLogin: 'Sign in',
    authRegister: 'Register',
    authUsername: 'Username',
    authPassword: 'Password',
    authAccessCode: 'Internal code (sales)',
    authGoRegister: 'Create an account',
    authGoLogin: 'Already have an account',
    authUsernameRequired: 'Enter a username',
    authPasswordRequired: 'Enter a password',
    authPasswordTooShort: 'Use at least 6 characters',
    authLoginSuccess: 'Signed in',
    authRegisterSuccess: 'Registered',
    favorites: 'Favorites',
    history: 'History',
    share: 'Share ↗',
    favoritesCountPrefix: '',
    favoritesCountSuffix: ' saved',
    exportFavoritesPdf: 'Export favorites PDF',
    recentPrefix: 'Recent ',
    recentSuffix: ' decors',
    refresh: 'Refresh',
    emptyFavorites: 'No favorites yet',
    emptyHistory: 'No browsing history yet',
    languageSwitch: '中文 / EN',
    shareTitle: 'schattdecor Sense',
    favoritesShareTitle: 'schattdecor Sense Favorites',
    homeTab: 'Home',
    cameraTab: 'Camera',
    mineTab: 'Mine',
    servicePageTitle: 'AI Service',
    serviceHideChat: 'Hide chat',
    serviceDate: 'Tue, Apr 14, 09:00',
    serviceBackTop: 'Back to top',
    serviceWelcome: 'Hello, I am Xia, your AI service assistant. Two quick questions help us connect you with the right sales contact. Your answers are only used for this matching and are protected.',
    serviceOccupationPrompt: 'Select the number for your profession so we can recommend the right sales contact.',
    serviceOccupationTitle: 'Your profession',
    serviceOccupationDesigner: 'Interior / soft furnishing designer',
    serviceOccupationManager: 'Home renovation project / site manager',
    serviceOccupationDistributor: 'Materials distributor or agent',
    serviceOccupationDeveloper: 'Property developer / procurement or designer',
    serviceOccupationStudent: 'Architecture or design student / teacher',
    serviceOccupationOwner: 'Homeowner / renovation decision maker',
    serviceOccupationBuilder: 'Independent tradesperson',
    serviceOccupationOther: 'Other',
    serviceRegionPrompt: 'Thank you. Select your region and we will provide the relevant sales contact.',
    serviceRegionTitle: 'Region',
    serviceRegionEast: 'East China',
    serviceRegionNorth: 'North China',
    serviceRegionSouth: 'South China',
    serviceRegionSouthwest: 'Southwest China',
    serviceRegionOverseas: 'Overseas',
    serviceRegionOther: 'Other',
    serviceContactIntro: 'Thank you. Your matched sales contact is:',
    serviceContactRegion: 'Region',
    serviceContactName: 'Sales contact',
    serviceContactPhone: 'Phone',
    serviceContactEmail: 'Email',
    serviceContactRegionValue: 'Southwest China',
    serviceCopyPhone: 'Copy phone only',
    serviceCopyFull: 'Copy all details',
    serviceInputPlaceholder: 'Enter a number...',
    serviceSend: 'Send',
    serviceOccupationInvalid: 'Please reply with a profession number from 1 to 8.',
    serviceRegionInvalid: 'Please reply with a region number from 1 to 6.',
    serviceCompleteHint: 'Contact details are ready. Reply 0 to restart matching.',
    serviceRestarted: 'Matching restarted. Please reply with your profession number.',
    copied: 'Copied'
  }
};

module.exports = {
  API_ENDPOINTS,
  AUTH_CONFIG,
  AUTH_MODES,
  BRAND,
  CATEGORY_ALIASES,
  CATEGORY_LABEL_KEYS,
  CATEGORY_OPTIONS,
  CATEGORY_VALUES,
  DEFAULT_APP_STATE,
  DEFAULT_LANGUAGE,
  ERROR_MESSAGES,
  EVENT_TYPES,
  FEEDBACK_VERDICTS,
  FILE_TYPES,
  FONT_CONFIG,
  FORM_LIMITS,
  HTTP_STATUS,
  I18N_DICTIONARIES,
  LANGUAGE_ORDER,
  LEAD_SOURCES,
  MATCH_MODES,
  MEDIA_CONFIG,
  MINE_TABS,
  NUMBER_FORMAT,
  PATTERN_DEFAULTS,
  REQUEST_METHODS,
  ROUTES,
  SEARCH_CONFIG,
  STORAGE_KEYS,
  TAB_BAR_LABEL_KEYS,
  TOAST_ICONS,
  UI_SYMBOLS,
  UI_TEXT,
  UNMATCHED_ERROR_CODES,
  UPLOAD_CONFIG,
  URL_PREFIXES,
  USERNAME_PREFIXES,
  USER_ROLES
};
