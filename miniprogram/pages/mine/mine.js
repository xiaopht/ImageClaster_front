// 页面依赖：api 负责后端交互，config 负责可调配置，i18n 负责多语言文案。
const api = require('../../utils/api');
const config = require('../../config');
const i18n = require('../../utils/i18n');
const visualMock = require('../../utils/visual-mock');

// 获取用户角色：影响访客、销售、内部账号的展示和权限判断。
function roleOf(user) {
  return (user && user.role) || config.USER_ROLES.visitor;
}

// 判断是否访客会话：影响“登录 / 注册”和访客名称的显示。
function isGuestSession(user) {
  const username = (user && user.username) || '';
  const accessMode = user && (user.access_mode || user.login_policy);
  return !user || accessMode === 'open' || (
    roleOf(user) === config.USER_ROLES.visitor
    && (!username || username.indexOf(config.USERNAME_PREFIXES.wechatVisitor) === 0)
  );
}

// 生成用户展示状态：影响我的页头像旁的名称、角色和访客标记。
function userState(user, text) {
  const role = roleOf(user);
  const guestSession = isGuestSession(user);
  const roleLabels = {};
  roleLabels[config.USER_ROLES.visitor] = text.roleVisitor;
  roleLabels[config.USER_ROLES.employee] = text.roleEmployee;
  roleLabels[config.USER_ROLES.sales] = text.roleSales;
  roleLabels[config.USER_ROLES.admin] = text.roleInternal;
  const guestName = i18n.currentLanguage() === 'en-US' ? 'Guest' : '游客';
  return {
    user,
    isVisitor: guestSession,
    displayName: user && !guestSession && user.username ? user.username : guestName,
    roleLabel: guestSession ? roleLabels[config.USER_ROLES.visitor] : (roleLabels[role] || role)
  };
}

Page({
  data: {
    brand: config.BRAND,
    icons: config.UI_SYMBOLS,
    tabs: config.MINE_TABS,
    authModes: config.AUTH_MODES,
    leadNoteMaxLength: config.FORM_LIMITS.leadNoteMaxLength,
    apiBase: '',
    language: i18n.DEFAULT_LANGUAGE,
    text: i18n.text(i18n.DEFAULT_LANGUAGE),
    user: null,
    displayName: i18n.text(i18n.DEFAULT_LANGUAGE).myName,
    roleLabel: '',
    isVisitor: true,
    authVisible: false,
    authMode: config.AUTH_MODES.login,
    authUsername: '',
    authPassword: '',
    authAccessCode: '',
    authLoading: false,
    leadVisible: false,
    leadLoading: false,
    leadIndustry: '',
    leadRegion: '',
    leadNote: '',
    leadContact: null,
    leadSource: config.LEAD_SOURCES.mine,
    activeTab: config.MINE_TABS.favorites,
    favorites: [],
    history: [],
    loading: false,
    detailVisible: false,
    detailSource: config.MINE_TABS.favorites,
    selectedIndex: 0,
    selectedItem: null,
    detailTotal: 0,
    detailCountText: config.UI_TEXT.emptyDetailCount,
    visualMockActive: false,
    visualState: '',
    visualSyntheticTabbar: false,
    authEntryVisible: false,
    roleLabelVisible: true
  },

  onLoad(options) {
    if (options && options.visualState) {
      this.setData({ visualState: options.visualState });
    }
  },

  onShow() {
    this.applyLanguage();
    const user = api.currentUser();
    this.setData(Object.assign({ apiBase: api.apiBase() }, userState(user, this.data.text)));
    if (this.data.visualState) {
      this.applyVisualState(this.data.visualState);
      return;
    }
    if (!api.currentToken() || !api.isAuthorizedUser(user)) {
      api.clearSession();
      const app = getApp();
      app.globalData.openPhoneLogin = true;
      wx.switchTab({ url: config.ROUTES.index });
      return;
    }
    api.validateSession().then((validatedUser) => {
      if (!api.isAuthorizedUser(validatedUser)) throw new Error('Phone login required');
      this.setData(userState(validatedUser, this.data.text));
      this.loadFavorites();
      this.loadHistory();
    }).catch(() => {
      api.clearSession();
      const app = getApp();
      app.globalData.openPhoneLogin = true;
      wx.switchTab({ url: config.ROUTES.index });
    });
  },

  applyLanguage() {
    const language = i18n.currentLanguage();
    const text = i18n.text(language);
    const user = api.currentUser() || this.data.user;
    this.setData(Object.assign({
      language,
      text,
      favorites: this.data.favorites.length ? api.formatPatternItems(this.data.favorites, this.data.apiBase, language) : [],
      history: this.data.history.length ? api.formatPatternItems(this.data.history, this.data.apiBase, language) : [],
      selectedItem: this.data.selectedItem ? api.formatPatternItems([this.data.selectedItem], this.data.apiBase, language)[0] : null
    }, userState(user, text)));
    i18n.applyTabBar(language);
  },

  applyVisualState(visualState) {
    const state = visualMock.stateFor(visualState, {
      config,
      text: this.data.text,
      formatItems: (items) => api.formatPatternItems(items, this.data.apiBase || api.apiBase(), this.data.language)
    });
    if (!state) return false;
    this.setData(state);
    return true;
  },

  toggleLanguage() {
    const language = i18n.setLanguage(i18n.nextLanguage(this.data.language));
    const user = api.currentUser() || this.data.user;
    if (user) {
      const updated = Object.assign({}, user, { language });
      wx.setStorageSync(config.STORAGE_KEYS.user, updated);
      getApp().globalData.user = updated;
      this.setData(userState(updated, i18n.text(language)));
    }
    this.applyLanguage();
    if (api.currentToken()) {
      api.updatePreferences(language).catch(() => {});
    }
  },

  switchTab(e) {
    this.setData({ activeTab: e.currentTarget.dataset.tab || config.MINE_TABS.favorites });
  },

  openAuth(e) {
    this.setData({
      authVisible: true,
      authMode: (e.currentTarget.dataset.mode || this.data.authMode || config.AUTH_MODES.login),
      authPassword: '',
      authLoading: false
    });
  },

  closeAuth() {
    if (this.data.authLoading) return;
    this.setData({ authVisible: false, authPassword: '' });
  },

  switchAuthMode(e) {
    this.setData({
      authMode: e.currentTarget.dataset.mode || config.AUTH_MODES.login,
      authPassword: '',
      authAccessCode: ''
    });
  },

  onAuthUsername(e) {
    this.setData({ authUsername: e.detail.value });
  },

  onAuthPassword(e) {
    this.setData({ authPassword: e.detail.value });
  },

  onAuthAccessCode(e) {
    this.setData({ authAccessCode: e.detail.value });
  },

  submitAuth() {
    if (this.data.authLoading) return;
    const username = this.data.authUsername.trim();
    const password = this.data.authPassword;
    const isRegister = this.data.authMode === config.AUTH_MODES.register;
    if (!username) {
      wx.showToast({ title: this.data.text.authUsernameRequired, icon: config.TOAST_ICONS.none });
      return;
    }
    if (!password) {
      wx.showToast({ title: this.data.text.authPasswordRequired, icon: config.TOAST_ICONS.none });
      return;
    }
    if (isRegister && password.length < config.AUTH_CONFIG.passwordMinLength) {
      wx.showToast({ title: this.data.text.authPasswordTooShort, icon: config.TOAST_ICONS.none });
      return;
    }

    const accessCode = this.data.authAccessCode.trim();
    this.setData({ authLoading: true });
    const action = isRegister
      ? api.register({
        username,
        password,
        role: accessCode ? config.USER_ROLES.sales : config.USER_ROLES.visitor,
        access_code: accessCode,
        language: this.data.language
      })
      : api.login({ username, password });

    action.then((res) => {
      const user = (res && res.user) || api.currentUser();
      const text = i18n.text(i18n.currentLanguage());
      this.applyLanguage();
      this.setData(Object.assign({
        authVisible: false,
        authPassword: '',
        authAccessCode: ''
      }, userState(user, text)));
      this.loadFavorites();
      this.loadHistory();
      wx.showToast({ title: isRegister ? this.data.text.authRegisterSuccess : this.data.text.authLoginSuccess });
    }).catch((error) => this.showError(error))
      .then(() => this.setData({ authLoading: false }));
  },

  loadFavorites() {
    this.setData({ loading: true });
    this.ensureVisitorSession()
      .then(() => api.listFavorites())
      .then((data) => this.setData({ favorites: this.formatItems(data.items || [], true) }))
      .catch((error) => this.showError(error))
      .then(() => this.setData({ loading: false }));
  },

  loadHistory() {
    this.ensureVisitorSession()
      .then(() => api.request({ url: config.API_ENDPOINTS.history(config.SEARCH_CONFIG.historyLimit) }))
      .then((data) => this.setData({ history: this.formatItems(data.items || [], false) }))
      .catch((error) => this.showError(error));
  },

  exportPdf() {
    const patternId = this.data.selectedItem && this.data.selectedItem.pattern_id;
    this.ensureVisitorSession().then(() => api.downloadPatternPdf(patternId))
      .then(() => wx.showToast({ title: this.data.text.pdfOpened }))
      .catch((error) => this.showError(error));
  },

  openItem(e) {
    const source = e.currentTarget.dataset.source || this.data.activeTab;
    this.showDetail(Number(e.currentTarget.dataset.index), source);
  },

  showDetail(index, source) {
    const detailSource = source || this.data.detailSource || this.data.activeTab;
    const list = this.detailList(detailSource);
    const total = list.length;
    if (!total) return;
    const selectedIndex = (index + total) % total;
    const selectedItem = list[selectedIndex];
    if (!selectedItem) return;
    this.setData({
      detailVisible: true,
      detailSource,
      selectedIndex,
      selectedItem,
      detailTotal: total,
      detailCountText: `${selectedIndex + 1}/${total}`
    });
    // 浏览记录中的详情预览不应改变记录顺序；从收藏打开详情仍会写入最新浏览。
    if (detailSource !== config.MINE_TABS.history) {
      this.recordBrowse(selectedItem.pattern_id);
    }
  },

  prevDetail() {
    this.showDetail(this.data.selectedIndex - 1, this.data.detailSource);
  },

  nextDetail() {
    this.showDetail(this.data.selectedIndex + 1, this.data.detailSource);
  },

  closeDetail() {
    this.setData({ detailVisible: false, selectedItem: null, detailTotal: 0 });
  },

  favorite(e) {
    const patternId = e.currentTarget.dataset.id;
    if (!patternId) return;
    const isFavorited = this.isFavorited(patternId);
    this.ensureVisitorSession().then(() => {
      return api.toggleFavorite(patternId, isFavorited);
    }).then((res) => {
      this.applyFavoritePatch(patternId, res.favorited);
      wx.showToast({ title: res.favorited ? this.data.text.favorited : this.data.text.favoriteRemoved });
    }).catch((error) => this.showError(error));
  },

  moreColors(e) {
    const patternId = e.currentTarget.dataset.id;
    const done = () => {
      wx.showToast({ title: this.data.text.demandRecorded, icon: config.TOAST_ICONS.none });
    };
    api.recordEvent(config.EVENT_TYPES.moreColors, patternId).then(done).catch(done);
  },

  contactService() {
    wx.navigateTo({
      url: config.ROUTES.service,
      fail: () => this.openLeadDialog(config.LEAD_SOURCES.mine)
    });
  },

  openLeadDialog(source) {
    this.setData({
      leadVisible: true,
      leadLoading: false,
      leadContact: null,
      leadSource: source || config.LEAD_SOURCES.mine
    });
  },

  closeLeadDialog() {
    if (this.data.leadLoading) return;
    this.setData({ leadVisible: false });
  },

  onLeadIndustry(e) {
    this.setData({ leadIndustry: e.detail.value });
  },

  onLeadRegion(e) {
    this.setData({ leadRegion: e.detail.value });
  },

  onLeadNote(e) {
    this.setData({ leadNote: e.detail.value });
  },

  submitLead() {
    if (this.data.leadLoading) return;
    const industry = this.data.leadIndustry.trim();
    const region = this.data.leadRegion.trim();
    const note = this.data.leadNote.trim();
    if (!industry || !region || !note) {
      wx.showToast({ title: this.data.text.leadRequired, icon: config.TOAST_ICONS.none });
      return;
    }
    this.setData({ leadLoading: true });
    api.submitLeadContact({
      industry,
      region,
      project_type: this.data.leadSource,
      note
    }).then((res) => {
      this.setData({ leadContact: res.contact || {} });
    }).catch((error) => {
      wx.showToast({ title: error.message || this.data.text.leadRetry, icon: config.TOAST_ICONS.none });
    }).then(() => this.setData({ leadLoading: false }));
  },

  recordBrowse(patternId) {
    if (!patternId) return;
    this.ensureVisitorSession().then(() => api.recordPatternView(patternId))
      .then((data) => {
        if (!data || !data.item) return;
        const item = this.formatItems([Object.assign({}, this.data.selectedItem || {}, data.item)], false)[0];
        this.syncPatternItem(patternId, item);
        this.moveHistoryToTop(patternId, item);
      })
      .catch(() => {});
  },

  syncPatternItem(patternId, item) {
    const updates = {};
    if (this.data.selectedItem && this.data.selectedItem.pattern_id === patternId) {
      updates.selectedItem = Object.assign({}, this.data.selectedItem, item);
    }
    this.data.favorites.forEach((favorite, index) => {
      if (favorite.pattern_id === patternId) {
        updates[`favorites[${index}]`] = Object.assign({}, favorite, item, { favorited: true });
      }
    });
    this.data.history.forEach((historyItem, index) => {
      if (historyItem.pattern_id === patternId) {
        updates[`history[${index}]`] = Object.assign({}, historyItem, item);
      }
    });
    if (Object.keys(updates).length) this.setData(updates);
  },

  moveHistoryToTop(patternId, item) {
    const current = this.data.history.filter((historyItem) => historyItem.pattern_id !== patternId);
    const existing = this.data.history.find((historyItem) => historyItem.pattern_id === patternId) || {};
    const nextItem = Object.assign({}, existing, item, { pattern_id: patternId });
    this.setData({ history: [nextItem].concat(current) });
  },

  detailList(source) {
    return source === config.MINE_TABS.history ? this.data.history : this.data.favorites;
  },

  isFavorited(patternId) {
    if (this.data.selectedItem && this.data.selectedItem.pattern_id === patternId) {
      return Boolean(this.data.selectedItem.favorited);
    }
    return this.data.favorites.some((item) => item.pattern_id === patternId)
      || this.data.history.some((item) => item.pattern_id === patternId && item.favorited);
  },

  applyFavoritePatch(patternId, favorited) {
    const updates = {};
    const sourceItem = this.data.selectedItem
      || this.data.history.find((item) => item.pattern_id === patternId)
      || this.data.favorites.find((item) => item.pattern_id === patternId);

    if (this.data.selectedItem && this.data.selectedItem.pattern_id === patternId) {
      updates['selectedItem.favorited'] = favorited;
    }
    this.data.history.forEach((item, index) => {
      if (item.pattern_id === patternId) updates[`history[${index}].favorited`] = favorited;
    });

    if (favorited) {
      let exists = false;
      this.data.favorites.forEach((item, index) => {
        if (item.pattern_id === patternId) {
          exists = true;
          updates[`favorites[${index}].favorited`] = true;
        }
      });
      if (!exists && sourceItem) {
        updates.favorites = [Object.assign({}, sourceItem, { favorited: true })].concat(this.data.favorites);
      }
    } else {
      updates.favorites = this.data.favorites.filter((item) => item.pattern_id !== patternId);
      if (this.data.detailSource === config.MINE_TABS.favorites) {
        updates.detailTotal = updates.favorites.length;
      }
    }
    this.setData(updates);
  },

  ensureVisitorSession() {
    return api.ensureVisitorSession().then((res) => {
      const user = (res && res.user) || api.currentUser();
      this.setData(userState(user, this.data.text));
      return res;
    });
  },

  formatItems(list, favorited) {
    return api.formatPatternItems(list, this.data.apiBase, this.data.language).map((item) => {
      return Object.assign({}, item, { favorited: favorited || Boolean(item.favorited) });
    });
  },

  noop() {},

  onShareAppMessage() {
    return {
      title: this.data.text.favoritesShareTitle,
      path: config.ROUTES.mine
    };
  },

  showError(error) {
    wx.showToast({ title: error.message || this.data.text.requestFailed, icon: config.TOAST_ICONS.none });
  }
});
