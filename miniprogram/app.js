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

    try {
      const apiBase = (this.globalData.apiBase || '').replace(/\/$/, '');
      const faces = config.FONT_CONFIG.faces && config.FONT_CONFIG.faces.length
        ? config.FONT_CONFIG.faces
        : [{ weight: '400', path: config.FONT_CONFIG.regularPath }];

      let finished = 0;
      let loaded = 0;
      const errors = [];

      const finish = () => {
        finished += 1;
        if (finished !== faces.length) return;

        this.globalData.fontLoaded = loaded > 0;
        this.globalData.fontLoadFailed = loaded === 0;
        this.globalData.fontLoadErrors = errors;

        if (errors.length) {
          console.warn('[font] HarmonyOS Sans SC load warnings:', errors);
        }
      };

      faces.forEach((face) => {
        const source = /^https?:\/\//.test(face.path)
          ? face.path
          : `${apiBase}${face.path}`;
        try {
          wx.loadFontFace({
            family: config.FONT_CONFIG.family,
            source: `url("${source}")`,
            desc: {
              style: 'normal',
              weight: face.weight
            },
            success: () => {
              loaded += 1;
            },
            fail: (error) => {
              errors.push({
                weight: face.weight,
                path: face.path,
                errMsg: error && error.errMsg ? error.errMsg : 'font load failed'
              });
            },
            complete: finish
          });
        } catch (error) {
          errors.push({
            weight: face.weight,
            path: face.path,
            errMsg: error && error.message ? error.message : 'font load exception'
          });
          finish();
        }
      });
    } catch (error) {
      this.globalData.fontLoaded = false;
      this.globalData.fontLoadFailed = true;
      this.globalData.fontLoadErrors = [{
        errMsg: error && error.message ? error.message : 'font setup exception'
      }];
      console.warn('[font] HarmonyOS Sans SC setup skipped:', this.globalData.fontLoadErrors);
    }
  }
});
