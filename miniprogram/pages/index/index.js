// 页面依赖：api 负责后端交互，config 负责可调配置，i18n 负责多语言文案。
const api = require('../../utils/api');
const config = require('../../config');
const i18n = require('../../utils/i18n');
const visualMock = require('../../utils/visual-mock');

// 客服悬浮按钮可调外观/位置参数（单位 rpx）：尺寸应与 app.wxss 的 `.service` 保持一致。
const SERVICE_FLOAT_STYLE = {
  width: 112, // 按钮宽度：数值越大，绿色客服浮钮越宽。
  height: 92, // 按钮高度：数值越大，图标和文字可用空间越多。
  sideGap: 24, // 左右最小安全边距：防止按钮贴住屏幕边缘。
  topGap: 128, // 拖动时距离窗口顶部的最小范围：避开状态栏和品牌区。
  bottomGap: 180, // 拖动时距离窗口底部的最小范围：避开 tabBar。
  defaultBottomGap: 335, // 首次显示时距离底部的默认位置：对应设计稿右下方位置。
  moveThreshold: 8 // 手指位移超过该数值后按“拖动”处理，不再触发进入客服页。
};

// 将设计用 rpx 换算为当前设备像素，使浮钮在不同屏幕宽度上的位置保持一致。
function serviceWindowMetrics() {
  const windowInfo = wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync();
  const windowWidth = windowInfo.windowWidth;
  const toPx = (value) => value * windowWidth / 750;
  const sideGap = toPx(SERVICE_FLOAT_STYLE.sideGap);
  const width = toPx(SERVICE_FLOAT_STYLE.width);
  const height = toPx(SERVICE_FLOAT_STYLE.height);
  return {
    sideGap,
    width,
    height,
    minTop: toPx(SERVICE_FLOAT_STYLE.topGap),
    maxLeft: Math.max(sideGap, windowWidth - width - sideGap),
    maxTop: Math.max(toPx(SERVICE_FLOAT_STYLE.topGap), windowInfo.windowHeight - height - toPx(SERVICE_FLOAT_STYLE.bottomGap)),
    defaultLeft: Math.max(sideGap, windowWidth - width - sideGap),
    defaultTop: Math.min(
      Math.max(toPx(SERVICE_FLOAT_STYLE.topGap), windowInfo.windowHeight - height - toPx(SERVICE_FLOAT_STYLE.bottomGap)),
      Math.max(toPx(SERVICE_FLOAT_STYLE.topGap), windowInfo.windowHeight - height - toPx(SERVICE_FLOAT_STYLE.defaultBottomGap))
    ),
    moveThreshold: toPx(SERVICE_FLOAT_STYLE.moveThreshold)
  };
}

Page({
  data: {
    brand: config.BRAND,
    matchModes: config.MATCH_MODES,
    feedbackNoteMaxLength: config.FORM_LIMITS.feedbackNoteMaxLength,
    leadNoteMaxLength: config.FORM_LIMITS.leadNoteMaxLength,
    apiBase: '',
    language: i18n.DEFAULT_LANGUAGE,
    text: i18n.text(i18n.DEFAULT_LANGUAGE),
    query: '',
    category: '',
    categoryOptions: i18n.categoryOptions(i18n.DEFAULT_LANGUAGE),
    matchMode: config.MATCH_MODES.auto,
    imagePath: '',
    results: [],
    resultCount: 0,
    recognitionId: '',
    recognition_id: '',
    threshold: 0,
    allTopResults: [],
    all_top_results: [],
    unmatchedDialogVisible: false,
    feedbackVisible: false,
    feedbackSubmitted: false,
    feedbackLoading: false,
    feedbackDialogVisible: false,
    feedbackStars: [1, 2, 3, 4, 5],
    feedbackRating: 0,
    feedbackDontRemind: false,
    feedbackCorrectPatternId: '',
    feedbackNote: '',
    leadVisible: false,
    leadLoading: false,
    leadIndustry: '',
    leadRegion: '',
    leadNote: '',
    leadContact: null,
    leadSource: config.LEAD_SOURCES.home,
    loading: false,
    message: '',
    serviceVisible: true,
    servicePositionReady: false,
    serviceLeft: 0,
    serviceTop: 0,
    detailVisible: false,
    selectedIndex: 0,
    selectedItem: null,
    detailCountText: config.UI_TEXT.emptyDetailCount,
    visualMockActive: false,
    visualState: '',
    visualSyntheticTabbar: false,
    searchBoxVisible: true,
    imagePanelMode: 'full',
    controlsVisible: true
  },

  onLoad(options) {
    this.applyLanguage();
    this.setData({ apiBase: api.apiBase() });
    this.applyVisualState(options && options.visualState);
  },

  onReady() {
    this.ensureServicePosition();
  },

  onResize() {
    if (!this.data.servicePositionReady) return;
    const metrics = serviceWindowMetrics();
    this.setData({
      serviceLeft: Math.min(metrics.maxLeft, Math.max(metrics.sideGap, this.data.serviceLeft)),
      serviceTop: Math.min(metrics.maxTop, Math.max(metrics.minTop, this.data.serviceTop))
    });
  },

  onShow() {
    this.applyLanguage();
    this.setData({ apiBase: api.apiBase() });
    if (this.data.visualMockActive) {
      this.applyVisualState(this.data.visualState);
      return;
    }
    this.refreshFavoriteState();
    this.openPendingHomeImagePicker();
  },

  // 消费底栏“拍照”的一次性请求，复用红框上传区域的选图/拍照和预览状态逻辑。
  openPendingHomeImagePicker() {
    const app = getApp();
    if (!app.globalData.openHomeImagePicker) return;
    app.globalData.openHomeImagePicker = false;
    const openPicker = () => this.chooseImage();
    if (wx.nextTick) {
      wx.nextTick(openPicker);
      return;
    }
    setTimeout(openPicker, 0);
  },

  applyLanguage() {
    const language = i18n.currentLanguage();
    const updates = {
      language,
      text: i18n.text(language),
      categoryOptions: i18n.categoryOptions(language)
    };
    if (this.data.results.length) {
      updates.results = api.formatPatternItems(this.data.results, this.data.apiBase, language);
    }
    if (this.data.selectedItem) {
      updates.selectedItem = api.formatPatternItems([this.data.selectedItem], this.data.apiBase, language)[0];
    }
    this.setData(updates);
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

  onQuery(e) {
    this.setData({ query: e.detail.value });
  },

  selectCategory(e) {
    this.setData({ category: e.currentTarget.dataset.value || '' });
  },

  selectMode(e) {
    this.setData({ matchMode: e.currentTarget.dataset.mode || config.MATCH_MODES.auto });
  },

  reset() {
    this.setData({
      query: '',
      category: '',
      matchMode: config.MATCH_MODES.auto,
      imagePath: '',
      results: [],
      resultCount: 0,
      recognitionId: '',
      recognition_id: '',
      threshold: 0,
      allTopResults: [],
      all_top_results: [],
      feedbackVisible: false,
      feedbackSubmitted: false,
      feedbackDialogVisible: false,
      unmatchedDialogVisible: false,
      feedbackRating: 0,
      feedbackDontRemind: false,
      feedbackCorrectPatternId: '',
      feedbackNote: '',
      message: '',
      detailVisible: false,
      selectedItem: null,
      detailCountText: config.UI_TEXT.emptyDetailCount,
      searchBoxVisible: true,
      imagePanelMode: 'full',
      controlsVisible: true
    });
  },

  chooseImage() {
    wx.chooseMedia({
      count: config.MEDIA_CONFIG.imageCount,
      mediaType: config.MEDIA_CONFIG.mediaTypes,
      sourceType: config.MEDIA_CONFIG.indexSourceTypes,
      success: (res) => {
        const filePath = res.tempFiles[0].tempFilePath;
        this.setData({
          imagePath: filePath,
          message: '',
          results: [],
          resultCount: 0,
          recognitionId: '',
          recognition_id: '',
          threshold: 0,
          allTopResults: [],
          all_top_results: [],
          feedbackVisible: false,
          feedbackSubmitted: false,
          feedbackLoading: false,
          feedbackDialogVisible: false,
          unmatchedDialogVisible: false,
          feedbackRating: 0,
          feedbackDontRemind: false,
          feedbackCorrectPatternId: '',
          feedbackNote: '',
          searchBoxVisible: true,
          imagePanelMode: 'full',
          controlsVisible: true
        });
      },
      fail: (error) => {
        if (error && error.errMsg && error.errMsg.indexOf('cancel') > -1) return;
        this.showError(error);
      }
    });
  },

  startSearch() {
    if (this.data.imagePath) {
      this.searchByImage();
      return;
    }
    if (this.data.query.trim()) {
      this.searchByText();
      return;
    }
    wx.showToast({ title: this.data.text.chooseImageOrKeyword, icon: config.TOAST_ICONS.none });
  },

  searchByImage() {
    this.setData({
      loading: true,
      message: this.data.text.matching,
      recognitionId: '',
      recognition_id: '',
      threshold: 0,
      allTopResults: [],
      all_top_results: [],
      feedbackVisible: false,
      feedbackSubmitted: false,
      feedbackLoading: false,
      feedbackDialogVisible: false,
      unmatchedDialogVisible: false,
      feedbackRating: 0,
      feedbackDontRemind: false,
      feedbackCorrectPatternId: '',
      feedbackNote: '',
      detailVisible: false,
      selectedItem: null
    });
    api.uploadRecognize(this.data.imagePath, this.data.category, this.data.matchMode === config.MATCH_MODES.auto)
      .then((data) => {
        const threshold = Number(data.threshold || 0);
        const topResults = data.top_results || data.results || [];
        const visibleResults = topResults.filter((item) => {
          return Number(item.confidence || 0) >= threshold;
        }).slice(0, config.SEARCH_CONFIG.imageResultLimit);
        const list = this.formatResults(visibleResults);
        const recognitionId = data.recognition_id || '';
        const allTopResults = data.all_top_results || topResults;
        const errorCode = data.error || data.status || '';
        const isUnmatched = config.UNMATCHED_ERROR_CODES.indexOf(errorCode) > -1;
        this.setData({
          results: list,
          resultCount: list.length,
          recognitionId,
          recognition_id: recognitionId,
          threshold,
          allTopResults,
          all_top_results: allTopResults,
          feedbackVisible: Boolean(recognitionId),
          feedbackSubmitted: false,
          unmatchedDialogVisible: isUnmatched,
          message: isUnmatched ? '' : (data.error ? (data.detail || this.data.text.noHighConfidence) : ''),
          searchBoxVisible: Boolean(isUnmatched && !list.length),
          imagePanelMode: 'full',
          controlsVisible: true
        });
        this.refreshFavoriteState();
      })
      .catch((error) => this.showError(error))
      .then(() => this.setData({ loading: false }));
  },

  searchByText() {
    this.setData({
      loading: true,
      message: this.data.text.searching,
      recognitionId: '',
      recognition_id: '',
      threshold: 0,
      allTopResults: [],
      all_top_results: [],
      feedbackVisible: false,
      feedbackSubmitted: false,
      feedbackLoading: false,
      feedbackDialogVisible: false,
      unmatchedDialogVisible: false
    });
    const url = config.API_ENDPOINTS.patternSearch(
      this.data.query.trim(),
      config.SEARCH_CONFIG.textResultLimit,
      config.SEARCH_CONFIG.textSearchMode,
      this.data.category
    );
    api.request({ url })
      .then((data) => {
        const list = this.formatResults(data.items || []);
        this.setData({
          results: list,
          resultCount: data.count || list.length,
          message: list.length ? '' : this.data.text.noTextResults,
          searchBoxVisible: true,
          imagePanelMode: list.length ? 'none' : 'full',
          controlsVisible: !list.length
        });
        this.refreshFavoriteState();
      }).catch((error) => this.showError(error))
      .then(() => this.setData({ loading: false }));
  },

  favorite(e) {
    const patternId = e.currentTarget.dataset.id;
    const index = Number(e.currentTarget.dataset.index);
    if (!patternId) return;
    const isFavorited = this.isFavorited(patternId, index);
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

  // 初始化客服浮钮位置：默认落在设计稿右下区域，拖动后使用手指选择的新位置。
  ensureServicePosition() {
    if (this.data.servicePositionReady) return;
    const metrics = serviceWindowMetrics();
    this.setData({
      servicePositionReady: true,
      serviceLeft: Math.round(metrics.defaultLeft),
      serviceTop: Math.round(metrics.defaultTop)
    });
  },

  // 记录按下起点：仅保存本次触摸，不会改变客服入口功能。
  startServiceDrag(e) {
    const touch = e.touches && e.touches[0];
    if (!touch) return;
    this.serviceDragState = {
      startX: touch.clientX,
      startY: touch.clientY,
      startLeft: this.data.serviceLeft,
      startTop: this.data.serviceTop,
      moved: false
    };
  },

  // 跟随手指移动并限制在可见内容区域，避免浮钮遮挡系统底栏或移出屏幕。
  moveServiceDrag(e) {
    const touch = e.touches && e.touches[0];
    const state = this.serviceDragState;
    if (!touch || !state) return;
    const metrics = serviceWindowMetrics();
    const deltaX = touch.clientX - state.startX;
    const deltaY = touch.clientY - state.startY;
    if (Math.abs(deltaX) > metrics.moveThreshold || Math.abs(deltaY) > metrics.moveThreshold) {
      state.moved = true;
    }
    this.setData({
      serviceLeft: Math.round(Math.min(metrics.maxLeft, Math.max(metrics.sideGap, state.startLeft + deltaX))),
      serviceTop: Math.round(Math.min(metrics.maxTop, Math.max(metrics.minTop, state.startTop + deltaY)))
    });
  },

  // 拖动停止后将浮钮吸附到最近的屏幕侧边，保留当前上下位置。
  snapServiceToEdge() {
    const metrics = serviceWindowMetrics();
    const centerX = this.data.serviceLeft + metrics.width / 2;
    const left = centerX < (metrics.maxLeft + metrics.sideGap + metrics.width) / 2
      ? metrics.sideGap
      : metrics.maxLeft;
    this.setData({ serviceLeft: Math.round(left) });
  },

  // 触摸结束时统一处理交互：发生位移则吸边，未位移则立即打开客服页面。
  endServiceDrag() {
    const state = this.serviceDragState;
    this.serviceDragState = null;
    if (!state) return;
    if (state.moved) {
      this.snapServiceToEdge();
      return;
    }
    this.contactService();
  },

  contactService() {
    wx.navigateTo({
      url: config.ROUTES.service,
      fail: () => this.openLeadDialog(this.data.results.length ? config.LEAD_SOURCES.homeResults : config.LEAD_SOURCES.home)
    });
  },

  openLeadDialog(source) {
    this.setData({
      leadVisible: true,
      leadLoading: false,
      leadContact: null,
      leadSource: source || config.LEAD_SOURCES.home
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

  feedbackPatternId() {
    const first = this.data.results[0];
    return (first && first.pattern_id) || '';
  },

  submitPositiveFeedback() {
    if (this.data.feedbackLoading || this.data.feedbackSubmitted || !this.data.recognitionId) return;
    this.setData({
      feedbackDialogVisible: true,
      feedbackRating: 4,
      feedbackDontRemind: false
    });
  },

  openFeedbackDialog() {
    if (this.data.feedbackLoading || this.data.feedbackSubmitted || !this.data.recognitionId) return;
    this.setData({
      feedbackDialogVisible: true,
      feedbackRating: 0,
      feedbackDontRemind: false,
      feedbackCorrectPatternId: '',
      feedbackNote: ''
    });
  },

  closeFeedbackDialog() {
    if (this.data.feedbackLoading) return;
    this.setData({ feedbackDialogVisible: false });
  },

  onFeedbackCorrectPattern(e) {
    this.setData({ feedbackCorrectPatternId: e.detail.value });
  },

  onFeedbackNote(e) {
    this.setData({ feedbackNote: e.detail.value });
  },

  selectFeedbackRating(e) {
    this.setData({ feedbackRating: Number(e.currentTarget.dataset.rating) || 0 });
  },

  toggleFeedbackDontRemind() {
    this.setData({ feedbackDontRemind: !this.data.feedbackDontRemind });
  },

  closeUnmatchedDialog() {
    this.setData({ unmatchedDialogVisible: false });
  },

  submitRatingFeedback() {
    if (this.data.feedbackLoading || this.data.feedbackSubmitted || !this.data.recognitionId) return;
    const rating = Number(this.data.feedbackRating || 0);
    const verdict = rating >= 4 ? config.FEEDBACK_VERDICTS.accurate : config.FEEDBACK_VERDICTS.inaccurate;
    const note = `rating=${rating}; dont_remind=${this.data.feedbackDontRemind ? 'true' : 'false'}`;
    this.submitRecognitionFeedback(verdict, this.feedbackPatternId(), '', note);
  },

  submitNegativeFeedback() {
    if (this.data.feedbackLoading || this.data.feedbackSubmitted || !this.data.recognitionId) return;
    this.submitRecognitionFeedback(
      config.FEEDBACK_VERDICTS.inaccurate,
      this.feedbackPatternId(),
      this.data.feedbackCorrectPatternId.trim(),
      this.data.feedbackNote.trim()
    );
  },

  submitRecognitionFeedback(verdict, patternId, correctPatternId, note) {
    this.setData({ feedbackLoading: true });
    api.submitFeedback({
      verdict,
      recognition_id: this.data.recognitionId,
      pattern_id: patternId || '',
      correct_pattern_id: correctPatternId || '',
      note: note || ''
    }).then(() => {
      this.setData({
        feedbackVisible: false,
        feedbackSubmitted: true,
        feedbackDialogVisible: false,
        feedbackCorrectPatternId: '',
        feedbackNote: ''
      });
      wx.showToast({ title: this.data.text.feedbackThanks, icon: config.TOAST_ICONS.none });
    }).catch((error) => {
      wx.showToast({ title: error.message || this.data.text.requestFailed, icon: config.TOAST_ICONS.none });
    }).then(() => this.setData({ feedbackLoading: false }));
  },

  hideService() {
    this.setData({ serviceVisible: false });
  },

  openDetail(e) {
    this.showDetail(Number(e.currentTarget.dataset.index));
  },

  showDetail(index) {
    const total = this.data.results.length;
    if (!total) return;
    const selectedIndex = (index + total) % total;
    const selectedItem = this.data.results[selectedIndex];
    if (!selectedItem) return;
    this.setData({
      detailVisible: true,
      selectedIndex,
      selectedItem,
      detailCountText: `${selectedIndex + 1}/${total}`
    });
    this.recordBrowse(selectedItem.pattern_id);
  },

  prevDetail() {
    this.showDetail(this.data.selectedIndex - 1);
  },

  nextDetail() {
    this.showDetail(this.data.selectedIndex + 1);
  },

  closeDetail() {
    this.setData({ detailVisible: false, selectedItem: null });
  },

  exportPdf() {
    const patternId = this.data.selectedItem && this.data.selectedItem.pattern_id;
    this.ensureVisitorSession().then(() => api.downloadPatternPdf(patternId))
      .then(() => wx.showToast({ title: this.data.text.pdfOpened }))
      .catch((error) => this.showError(error));
  },

  recordBrowse(patternId) {
    if (!patternId) return;
    this.ensureVisitorSession().then(() => api.recordPatternView(patternId))
      .then((data) => {
        if (!data || !data.item || !this.data.selectedItem || this.data.selectedItem.pattern_id !== patternId) return;
        const item = this.formatResults([Object.assign({}, this.data.selectedItem, data.item)])[0];
        const updates = { selectedItem: item };
        const index = this.data.results.findIndex((result) => result.pattern_id === patternId);
        if (index > -1) updates[`results[${index}]`] = item;
        this.setData(updates);
      })
      .catch(() => {});
  },

  noop() {},

  ensureVisitorSession() {
    return api.ensureVisitorSession();
  },

  refreshFavoriteState() {
    if (!wx.getStorageSync('token') || !this.data.results.length) return;
    api.listFavorites().then((data) => {
      const results = api.applyFavoriteState(this.data.results, data.items || []);
      const updates = { results };
      if (this.data.selectedItem) {
        updates.selectedItem = api.applyFavoriteState([this.data.selectedItem], data.items || [])[0];
      }
      this.setData(updates);
    }).catch(() => {});
  },

  isFavorited(patternId, index) {
    if (this.data.selectedItem && this.data.selectedItem.pattern_id === patternId) {
      return Boolean(this.data.selectedItem.favorited);
    }
    const item = this.data.results[index];
    return Boolean(item && item.favorited);
  },

  applyFavoritePatch(patternId, favorited) {
    const updates = {};
    this.data.results.forEach((item, index) => {
      if (item.pattern_id === patternId) updates[`results[${index}].favorited`] = favorited;
    });
    if (this.data.selectedItem && this.data.selectedItem.pattern_id === patternId) {
      updates['selectedItem.favorited'] = favorited;
    }
    this.setData(updates);
  },

  formatResults(list) {
    return api.formatPatternItems(list, this.data.apiBase, this.data.language);
  },

  onShareAppMessage() {
    return {
      title: this.data.text.shareTitle,
      path: config.ROUTES.index
    };
  },

  showError(error) {
    this.setData({ loading: false, message: '' });
    wx.showToast({ title: error.message || this.data.text.requestFailed, icon: config.TOAST_ICONS.none });
  }
});
