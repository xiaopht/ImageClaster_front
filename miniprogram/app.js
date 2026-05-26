const config = require('./config');

App({
  globalData: Object.assign({}, config.DEFAULT_APP_STATE),

  onLaunch() {
    const apiBase = wx.getStorageSync(config.STORAGE_KEYS.apiBase);
    const token = wx.getStorageSync(config.STORAGE_KEYS.token);
    const user = wx.getStorageSync(config.STORAGE_KEYS.user);
    const language = wx.getStorageSync(config.STORAGE_KEYS.language) || (user && user.language);

    if (apiBase) this.globalData.apiBase = apiBase;
    if (token) this.globalData.token = token;
    if (user) this.globalData.user = user;
    if (language) this.globalData.language = language;

    this.loadHarmonyFont();
  },

  loadHarmonyFont() {
    if (!wx.loadFontFace || this.globalData.fontLoaded) return;

    const apiBase = (this.globalData.apiBase || '').replace(/\/$/, '');
    const faces = config.FONT_CONFIG.faces && config.FONT_CONFIG.faces.length
      ? config.FONT_CONFIG.faces
      : [{ weight: '400', path: config.FONT_CONFIG.regularPath }];

    let finished = 0;
    let loaded = 0;

    faces.forEach((face) => {
      wx.loadFontFace({
        family: config.FONT_CONFIG.family,
        source: `url("${apiBase}${face.path}")`,
        desc: {
          style: 'normal',
          weight: face.weight
        },
        success: () => {
          loaded += 1;
        },
        complete: () => {
          finished += 1;
          if (finished === faces.length && loaded > 0) {
            this.globalData.fontLoaded = true;
          }
        }
      });
    });
  }
});
