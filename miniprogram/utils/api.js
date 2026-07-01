// 项目配置：影响接口路径、存储键、角色、上传参数和错误提示。
const config = require('../config');
// 多语言工具：影响会话保存和花色分类标签的语言展示。
const i18n = require('./i18n');

// 获取全局状态：影响 API 基础地址、登录态和用户信息的统一读取。
function appState() {
  return getApp().globalData;
}

// 获取接口基础地址：优先使用本地覆盖配置，影响所有后端请求。
function apiBase() {
  return wx.getStorageSync(config.STORAGE_KEYS.apiBase) || appState().apiBase;
}

// 获取当前 token：影响需要鉴权的接口请求头。
function currentToken() {
  return wx.getStorageSync(config.STORAGE_KEYS.token) || appState().token;
}

// 获取当前用户：影响访客态、角色和语言偏好判断。
function currentUser() {
  return wx.getStorageSync(config.STORAGE_KEYS.user) || appState().user || null;
}

// 只有后台已配置手机号且账号有效的员工才视为正式登录。
function isAuthorizedUser(user) {
  const role = user && user.role;
  const accessMode = user && (user.access_mode || user.login_policy);
  return Boolean(
    user
    && user.status !== 'disabled'
    && (
      [config.USER_ROLES.employee, config.USER_ROLES.sales, config.USER_ROLES.admin].indexOf(role) > -1
      || (role === config.USER_ROLES.visitor && accessMode === 'open')
    )
  );
}

// 生成鉴权请求头：影响所有带 token 的接口访问。
function authHeader(extra) {
  const token = currentToken();
  const header = Object.assign({}, extra || {});
  if (token) header.Authorization = `${config.AUTH_CONFIG.tokenScheme} ${token}`;
  return header;
}

// 保存登录会话：影响 token、用户信息和用户语言偏好的本地持久化。
function saveSession(result) {
  if (!result || !result.token) return;
  const user = result.user ? Object.assign({ role: config.USER_ROLES.visitor }, result.user) : null;
  appState().token = result.token;
  appState().user = user;
  validatedToken = result.token;
  wx.setStorageSync(config.STORAGE_KEYS.token, result.token);
  wx.setStorageSync(config.STORAGE_KEYS.user, user);
  if (user && user.language) {
    i18n.setLanguage(user.language);
  }
}

// 统一请求方法：影响所有 JSON 接口的地址、方法、数据和错误处理。
function request(options) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${apiBase()}${options.url}`,
      method: options.method || config.REQUEST_METHODS.get,
      data: options.data || {},
      header: authHeader(options.header),
      success(res) {
        if (res.statusCode >= config.HTTP_STATUS.successMin && res.statusCode < config.HTTP_STATUS.successMax) {
          resolve(res.data);
        } else {
          const error = new Error((res.data && res.data.detail) || `${config.ERROR_MESSAGES.httpPrefix} ${res.statusCode}`);
          error.statusCode = res.statusCode;
          error.responseData = res.data;
          reject(error);
        }
      },
      fail: reject
    });
  });
}

// 注册账号：影响我的页注册流程。
function register(data) {
  return request({ url: config.API_ENDPOINTS.register, method: config.REQUEST_METHODS.post, data }).then((res) => {
    saveSession(res);
    return res;
  });
}

// 登录账号：影响我的页登录流程。
function login(data) {
  return request({ url: config.API_ENDPOINTS.login, method: config.REQUEST_METHODS.post, data }).then((res) => {
    saveSession(res);
    return res;
  });
}

// 使用微信手机号动态 code 与 wx.login code 登录；手机号只在后端向微信换取。
function wechatPhoneLogin(phoneCode, loginCode, devOptions) {
  const options = devOptions || {};
  return request({
    url: config.API_ENDPOINTS.wechatPhoneLogin,
    method: config.REQUEST_METHODS.post,
    data: {
      phone_code: phoneCode || '',
      login_code: loginCode || '',
      dev_phone: options.devPhone || '',
      dev_openid: options.devOpenid || '',
      language: i18n.currentLanguage()
    }
  }).then((res) => {
    saveSession(res);
    return res;
  });
}

function validateSession() {
  const token = currentToken();
  if (!token) return Promise.reject(Object.assign(new Error('Login required'), { statusCode: 401 }));
  return request({ url: config.API_ENDPOINTS.authMe }).then((res) => {
    const user = res && res.user;
    if (user) {
      appState().user = user;
      wx.setStorageSync(config.STORAGE_KEYS.user, user);
    }
    validatedToken = token;
    return user;
  });
}

// 微信登录：影响访客会话创建和开发环境 openid 兜底。
function wechatLogin(role, accessCode) {
  return new Promise((resolve, reject) => {
    let devOpenid = wx.getStorageSync(config.STORAGE_KEYS.devOpenid);
    if (!devOpenid) {
      devOpenid = `${config.AUTH_CONFIG.devOpenidPrefix}${Date.now()}_${Math.random().toString(config.AUTH_CONFIG.randomRadix).slice(config.AUTH_CONFIG.randomSliceStart)}`;
      wx.setStorageSync(config.STORAGE_KEYS.devOpenid, devOpenid);
    }
    wx.login({
      success(loginRes) {
        request({
          url: config.API_ENDPOINTS.wechatLogin,
          method: config.REQUEST_METHODS.post,
          data: {
            code: loginRes.code,
            dev_openid: devOpenid,
            role: role || config.USER_ROLES.visitor,
            access_code: accessCode || '',
            language: i18n.currentLanguage()
          }
        }).then((res) => {
          saveSession(res);
          resolve(res);
        }).catch(reject);
      },
      fail: reject
    });
  });
}

// 会话校验 Promise：避免多个页面同时验证同一个员工 token。
let visitorSessionPromise = null;
let validatedToken = '';

// 清除失效或属于旧 AppID 的本地会话，避免前端继续携带无效 token。
function clearSession() {
  validatedToken = '';
  appState().token = '';
  appState().user = null;
  wx.removeStorageSync(config.STORAGE_KEYS.token);
  wx.removeStorageSync(config.STORAGE_KEYS.user);
}

function createVisitorSession() {
  return wechatLogin(config.USER_ROLES.visitor).then((res) => {
    validatedToken = res.token || '';
    return res;
  });
}

// 确保存在有效员工会话：收藏、浏览、反馈等操作不再创建匿名访客账号。
function ensureVisitorSession() {
  const token = currentToken();
  if (!token) {
    return Promise.reject(new Error('Phone login required'));
  }
  if (token && validatedToken === token) {
    return Promise.resolve({ token, user: currentUser() });
  }
  if (visitorSessionPromise) return visitorSessionPromise;

  const establishSession = token
    ? request({ url: config.API_ENDPOINTS.authMe })
      .then((res) => {
        validatedToken = token;
        if (res && res.user) {
          appState().user = res.user;
          wx.setStorageSync(config.STORAGE_KEYS.user, res.user);
        }
        return { token, user: (res && res.user) || currentUser() };
      })
      .catch((error) => {
        if (error.statusCode !== 401) throw error;
        clearSession();
        throw new Error('Phone login required');
      })
    : Promise.reject(new Error('Phone login required'));

  visitorSessionPromise = establishSession
    .then((res) => {
      visitorSessionPromise = null;
      return res;
    })
    .catch((error) => {
      visitorSessionPromise = null;
      throw error;
    });
  return visitorSessionPromise;
}

// 上传图片并识别：影响首页和拍摄页的图片匹配流程。
function uploadRecognize(filePath, category, useCrop) {
  let uploadTask = null;
  const promise = new Promise((resolve, reject) => {
    const formData = {};
    formData[config.UPLOAD_CONFIG.cropFieldName] = useCrop === false ? config.UPLOAD_CONFIG.cropDisabledValue : config.UPLOAD_CONFIG.cropEnabledValue;
    formData[config.UPLOAD_CONFIG.categoryFieldName] = category || '';
    uploadTask = wx.uploadFile({
      url: `${apiBase()}${config.API_ENDPOINTS.recognize}`,
      filePath,
      name: config.UPLOAD_CONFIG.fileFieldName,
      header: authHeader(),
      formData,
      success(res) {
        try {
          const data = JSON.parse(res.data);
          if (res.statusCode >= config.HTTP_STATUS.successMin && res.statusCode < config.HTTP_STATUS.successMax) {
            resolve(data);
          } else {
            reject(new Error(data.detail || `${config.ERROR_MESSAGES.httpPrefix} ${res.statusCode}`));
          }
        } catch (error) {
          reject(error);
        }
      },
      fail: reject
    });
  });
  promise.abort = () => {
    if (uploadTask && typeof uploadTask.abort === 'function') {
      uploadTask.abort();
    }
  };
  return promise;
}

// 补全花色图片地址：影响花色卡片和详情页图片显示。
function normalizePatternImageUrl(imageUrl, patternId, base) {
  const rawImageUrl = imageUrl || '';
  const resolvedPatternId = patternId || '';
  if (
    rawImageUrl.indexOf(config.URL_PREFIXES.http) === 0
    || rawImageUrl.indexOf(config.URL_PREFIXES.wxFile) === 0
    || rawImageUrl.indexOf(config.URL_PREFIXES.blob) === 0
  ) {
    return rawImageUrl;
  }
  // 视觉回归和本地静态资源允许直接使用小程序包内 assets，避免被拼成后端 HTTP 地址。
  if (rawImageUrl.indexOf('/assets/') === 0) return rawImageUrl;
  if (rawImageUrl) return `${base || apiBase()}${rawImageUrl}`;
  if (resolvedPatternId) return `${base || apiBase()}${config.API_ENDPOINTS.patternImage(resolvedPatternId)}`;
  return '';
}

function patternImageUrl(item, base) {
  const patternId = item.pattern_id || item.id || item.code || '';
  const imageUrl = item.thumbnail_url || item.thumbnail || item.image_url || item.image || '';
  return normalizePatternImageUrl(imageUrl, patternId, base);
}

function patternFullImageUrl(item, base) {
  const patternId = item.pattern_id || item.id || item.code || '';
  const imageUrl = item.full_image_url || item.fullImageUrl || item.image || item.image_url || item.thumbnail_url || item.thumbnail || '';
  return normalizePatternImageUrl(imageUrl, patternId, base);
}

// 格式化花色列表：影响所有页面卡片所需的名称、编号、分类、图片和收藏态字段。
function formatPatternItems(list, base, language) {
  const activeLanguage = language || i18n.currentLanguage();
  return (list || []).map((item) => {
    const confidence = Number(item.confidence || 0);
    const patternId = item.pattern_id || item.id || item.code || '';
    const name = item.decor_name || item.name || item.pattern_name || patternId || config.PATTERN_DEFAULTS.unnamedName;
    const category = item.category || item.texture_name || item.usage_name || item.wood_art_name || config.PATTERN_DEFAULTS.category;
    return Object.assign({}, item, {
      pattern_id: patternId,
      nameText: name,
      idText: item.code || patternId,
      categoryLabel: i18n.categoryLabel(category, activeLanguage),
      imageSrc: patternImageUrl(item, base),
      fullImageSrc: patternFullImageUrl(item, base),
      confidenceText: confidence ? `${Math.round(confidence * config.NUMBER_FORMAT.percentMultiplier)}%` : '',
      favorited: Boolean(item.favorited)
    });
  });
}

// 生成收藏 ID 映射：影响批量同步收藏态的查找效率。
function favoriteIdMap(items) {
  const ids = {};
  (items || []).forEach((item) => {
    const patternId = item.pattern_id || item.id || item.code;
    if (patternId) ids[patternId] = true;
  });
  return ids;
}

// 应用收藏状态：影响搜索结果、收藏列表和浏览记录中的星标状态。
function applyFavoriteState(items, favoriteItems) {
  const ids = favoriteIdMap(favoriteItems);
  return (items || []).map((item) => {
    return Object.assign({}, item, { favorited: Boolean(ids[item.pattern_id] || item.favorited) });
  });
}

// 记录花色浏览并读取详情：后端详情接口会保存本次详情浏览记录。
function recordPatternView(patternId) {
  if (!patternId) return Promise.resolve({});
  return request({ url: config.API_ENDPOINTS.patternDetail(patternId) });
}

// 获取收藏列表：影响我的收藏和搜索结果收藏态同步。
function listFavorites() {
  return request({ url: config.API_ENDPOINTS.favorites });
}

// 切换收藏状态：影响收藏和取消收藏请求。
function toggleFavorite(patternId, isFavorited) {
  if (!patternId) return Promise.resolve({ favorited: false });
  if (isFavorited) {
    return request({
      url: config.API_ENDPOINTS.favoriteItem(patternId),
      method: config.REQUEST_METHODS.delete
    }).then(() => ({ favorited: false }));
  }
  return request({
    url: config.API_ENDPOINTS.favorites,
    method: config.REQUEST_METHODS.post,
    data: { pattern_id: patternId }
  }).then(() => ({ favorited: true }));
}

// 记录用户事件：影响更多颜色等行为上报。
function recordEvent(eventType, patternId, payload) {
  return ensureVisitorSession().then(() => {
    return request({
      url: config.API_ENDPOINTS.events,
      method: config.REQUEST_METHODS.post,
      data: {
        event_type: eventType,
        pattern_id: patternId || '',
        payload: payload || {}
      }
    });
  });
}

// 提交识别反馈：影响准确/不准确反馈的后端记录。
function submitFeedback(data) {
  return ensureVisitorSession().then(() => {
    return request({
      url: config.API_ENDPOINTS.feedback,
      method: config.REQUEST_METHODS.post,
      data: data || {}
    });
  });
}

// 提交销售线索：影响进一步沟通弹窗的联系方式返回。
function submitLeadContact(data) {
  return ensureVisitorSession().then(() => {
    return request({
      url: config.API_ENDPOINTS.leadContact,
      method: config.REQUEST_METHODS.post,
      data: data || {}
    });
  });
}

// 提交客服对话后的结构化线索：职业、区域、销售联系方式和简要对话会进入后台“客服线索”。
function submitServiceLead(data) {
  return ensureVisitorSession().then(() => {
    return request({
      url: config.API_ENDPOINTS.serviceLead,
      method: config.REQUEST_METHODS.post,
      data: data || {}
    });
  });
}

// 更新用户偏好：影响登录用户语言选择同步到后端。
function updatePreferences(language) {
  return request({
    url: config.API_ENDPOINTS.userPreferences,
    method: config.REQUEST_METHODS.post,
    data: { language }
  }).then((res) => {
    if (res && res.user) {
      const stored = wx.getStorageSync(config.STORAGE_KEYS.user) || {};
      const merged = Object.assign({}, stored, res.user);
      appState().user = merged;
      wx.setStorageSync(config.STORAGE_KEYS.user, merged);
      i18n.setLanguage(res.user.language);
    }
    return res;
  });
}

// 下载收藏合集 PDF：保留为后台/未来批量导出能力，当前“我的”列表页不展示此入口。
function downloadFavoritesPdf() {
  return new Promise((resolve, reject) => {
    wx.downloadFile({
      url: `${apiBase()}${config.API_ENDPOINTS.favoritesPdf}`,
      header: authHeader(),
      success(res) {
        if (res.statusCode >= config.HTTP_STATUS.successMin && res.statusCode < config.HTTP_STATUS.successMax) {
          wx.openDocument({
            filePath: res.tempFilePath,
            fileType: config.FILE_TYPES.pdf,
            showMenu: true,
            success: () => resolve(res.tempFilePath),
            fail: reject
          });
        } else {
          reject(new Error(`${config.ERROR_MESSAGES.httpPrefix} ${res.statusCode}`));
        }
      },
      fail: reject
    });
  });
}

// 下载单个花色 PDF：影响详情弹层导出 PDF 功能。
function downloadPatternPdf(patternId) {
  return new Promise((resolve, reject) => {
    if (!patternId) {
      reject(new Error(config.ERROR_MESSAGES.patternRequired));
      return;
    }
    wx.downloadFile({
      url: `${apiBase()}${config.API_ENDPOINTS.patternPdf(patternId)}`,
      header: authHeader(),
      success(res) {
        if (res.statusCode >= config.HTTP_STATUS.successMin && res.statusCode < config.HTTP_STATUS.successMax) {
          wx.openDocument({
            filePath: res.tempFilePath,
            fileType: config.FILE_TYPES.pdf,
            showMenu: true,
            success: () => resolve(res.tempFilePath),
            fail: reject
          });
        } else {
          reject(new Error(`${config.ERROR_MESSAGES.httpPrefix} ${res.statusCode}`));
        }
      },
      fail: reject
    });
  });
}

module.exports = {
  apiBase,
  currentToken,
  currentUser,
  isAuthorizedUser,
  request,
  register,
  login,
  wechatPhoneLogin,
  validateSession,
  wechatLogin,
  ensureVisitorSession,
  uploadRecognize,
  recordPatternView,
  listFavorites,
  toggleFavorite,
  recordEvent,
  submitFeedback,
  submitLeadContact,
  submitServiceLead,
  applyFavoriteState,
  updatePreferences,
  downloadFavoritesPdf,
  downloadPatternPdf,
  saveSession,
  clearSession,
  patternImageUrl,
  formatPatternItems
};
