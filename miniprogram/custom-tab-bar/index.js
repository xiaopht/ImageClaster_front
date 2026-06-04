const i18n = require('../utils/i18n');

const TAB_ITEMS = [
  {
    pagePath: '/pages/index/index',
    labelKey: 'homeTab',
    iconClass: 'svg-icon-home-normal',
    selectedIconClass: 'svg-icon-home-active'
  },
  {
    pagePath: '/pages/camera/camera',
    labelKey: 'cameraTab',
    iconClass: 'svg-icon-camera-normal',
    selectedIconClass: 'svg-icon-camera-active'
  },
  {
    pagePath: '/pages/mine/mine',
    labelKey: 'mineTab',
    iconClass: 'svg-icon-mine-normal',
    selectedIconClass: 'svg-icon-mine-active'
  }
];

Component({
  data: {
    selected: 0,
    language: i18n.DEFAULT_LANGUAGE,
    list: []
  },

  lifetimes: {
    attached() {
      this.refresh();
    }
  },

  pageLifetimes: {
    show() {
      this.refresh();
    }
  },

  methods: {
    buildList(language) {
      const dict = i18n.text(language);
      return TAB_ITEMS.map((item) => {
        return {
          pagePath: item.pagePath,
          text: dict[item.labelKey],
          iconClass: item.iconClass,
          selectedIconClass: item.selectedIconClass
        };
      });
    },

    currentIndex() {
      const pages = getCurrentPages();
      const current = pages[pages.length - 1];
      const route = current && current.route ? `/${current.route}` : TAB_ITEMS[0].pagePath;
      const index = TAB_ITEMS.findIndex((item) => item.pagePath === route);
      return index > -1 ? index : 0;
    },

    refresh() {
      const language = i18n.currentLanguage();
      this.setData({
        language,
        selected: this.currentIndex(),
        list: this.buildList(language)
      });
    },

    setLanguage(language) {
      const normalized = i18n.normalizeLanguage(language);
      this.setData({
        language: normalized,
        selected: this.currentIndex(),
        list: this.buildList(normalized)
      });
    },

    switchTab(e) {
      const index = Number(e.currentTarget.dataset.index);
      const item = TAB_ITEMS[index];
      if (!item) return;
      wx.switchTab({ url: item.pagePath });
    }
  }
});
