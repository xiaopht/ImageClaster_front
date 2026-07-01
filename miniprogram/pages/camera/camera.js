// 页面依赖：api 负责后端交互，config 负责可调配置，i18n 负责多语言文案。
const api = require('../../utils/api');
const config = require('../../config');
const i18n = require('../../utils/i18n');
const visualMock = require('../../utils/visual-mock');

Page({
  activeRecognitionTask: null,
  recognitionRunId: 0,

  data: {
    brand: config.BRAND,
    icons: config.UI_SYMBOLS,
    matchModes: config.MATCH_MODES,
    feedbackNoteMaxLength: config.FORM_LIMITS.feedbackNoteMaxLength,
    apiBase: '',
    language: i18n.DEFAULT_LANGUAGE,
    text: i18n.text(i18n.DEFAULT_LANGUAGE),
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
    feedbackVisible: false,
    feedbackSubmitted: false,
    feedbackLoading: false,
    feedbackDialogVisible: false,
    feedbackCorrectPatternId: '',
    feedbackNote: '',
    loading: false,
    message: '',
    detailVisible: false,
    selectedIndex: 0,
    selectedItem: null,
    detailCountText: config.UI_TEXT.emptyDetailCount,
    visualMockActive: false,
    visualState: ''
  },

  onLoad(options) {
    this.applyLanguage();
    this.setData({ apiBase: api.apiBase() });
    this.applyVisualState(options && options.visualState);
  },

  // 中止当前图片识别，防止页面切换或再次识别后旧请求继续写入结果。
  cancelActiveRecognition() {
    this.recognitionRunId = (this.recognitionRunId || 0) + 1;
    if (this.activeRecognitionTask && typeof this.activeRecognitionTask.abort === 'function') {
      this.activeRecognitionTask.abort();
    }
    this.activeRecognitionTask = null;
  },

  onShow() {
    this.applyLanguage();
    this.setData({ apiBase: api.apiBase() });
    if (this.data.visualMockActive) {
      this.applyVisualState(this.data.visualState);
      return;
    }
    if (!api.currentToken() || !api.isAuthorizedUser(api.currentUser())) {
      const app = getApp();
      app.globalData.openPhoneLogin = true;
      app.globalData.openHomeImagePicker = false;
      wx.switchTab({ url: config.ROUTES.index });
      return;
    }
    this.openHomeCaptureShortcut();
  },

  // 底栏“拍照”是首页上传区域的快捷入口：回到首页后由首页调用同一套选图流程。
  openHomeCaptureShortcut() {
    const app = getApp();
    app.globalData.openHomeImagePicker = true;
    wx.switchTab({
      url: config.ROUTES.index,
      fail: (error) => {
        app.globalData.openHomeImagePicker = false;
        this.showError(error);
      }
    });
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

  chooseImage() {
    wx.chooseMedia({
      count: config.MEDIA_CONFIG.imageCount,
      mediaType: config.MEDIA_CONFIG.mediaTypes,
      sourceType: config.MEDIA_CONFIG.cameraSourceTypes,
      success: (res) => {
        this.cancelActiveRecognition();
        this.setData({
          imagePath: res.tempFiles[0].tempFilePath,
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
          feedbackCorrectPatternId: '',
          feedbackNote: '',
          message: '',
          detailVisible: false,
          selectedItem: null
        });
      },
      fail: (error) => {
        if (error && error.errMsg && error.errMsg.indexOf('cancel') > -1) return;
        this.showError(error);
      }
    });
  },

  selectCategory(e) {
    this.setData({ category: e.currentTarget.dataset.value || '' });
  },

  selectMode(e) {
    this.setData({ matchMode: e.currentTarget.dataset.mode || config.MATCH_MODES.auto });
  },

  startSearch() {
    if (!this.data.imagePath) {
      wx.showToast({ title: this.data.text.chooseImageFirst, icon: config.TOAST_ICONS.none });
      return;
    }
    const runId = (this.recognitionRunId || 0) + 1;
    this.recognitionRunId = runId;
    if (this.activeRecognitionTask && typeof this.activeRecognitionTask.abort === 'function') {
      this.activeRecognitionTask.abort();
    }
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
      feedbackCorrectPatternId: '',
      feedbackNote: '',
      detailVisible: false,
      selectedItem: null
    });
    const recognitionTask = api.uploadRecognize(this.data.imagePath, this.data.category, this.data.matchMode === config.MATCH_MODES.auto);
    this.activeRecognitionTask = recognitionTask;
    recognitionTask
      .then((data) => {
        if (this.recognitionRunId !== runId) return;
        const threshold = Number(data.threshold || 0);
        const topResults = data.top_results || data.results || [];
        const visibleResults = topResults.filter((item) => {
          return Number(item.confidence || 0) >= threshold;
        }).slice(0, config.SEARCH_CONFIG.imageResultLimit);
        const list = api.formatPatternItems(visibleResults, this.data.apiBase, this.data.language);
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
          message: isUnmatched ? this.data.text.dataUnmatchedAdvice : (data.error ? (data.detail || this.data.text.noHighConfidence) : '')
        });
        this.refreshFavoriteState();
      })
      .catch((error) => {
        if (this.recognitionRunId !== runId) return;
        this.showError(error);
      })
      .then(() => {
        if (this.recognitionRunId !== runId) return;
        this.activeRecognitionTask = null;
        this.setData({ loading: false });
      });
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

  feedbackPatternId() {
    const first = this.data.results[0];
    return (first && first.pattern_id) || '';
  },

  submitPositiveFeedback() {
    if (this.data.feedbackLoading || this.data.feedbackSubmitted || !this.data.recognitionId) return;
    this.submitRecognitionFeedback(config.FEEDBACK_VERDICTS.accurate, this.feedbackPatternId(), '', '');
  },

  openFeedbackDialog() {
    if (this.data.feedbackLoading || this.data.feedbackSubmitted || !this.data.recognitionId) return;
    this.setData({
      feedbackDialogVisible: true,
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
        const item = api.formatPatternItems([Object.assign({}, this.data.selectedItem, data.item)], this.data.apiBase, this.data.language)[0];
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
    if (!this.data.results.length) return;
    this.ensureVisitorSession().then(() => api.listFavorites()).then((data) => {
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

  showError(error) {
    this.setData({ loading: false });
    wx.showToast({ title: error.message || this.data.text.requestFailed, icon: config.TOAST_ICONS.none });
  }
});
