// 项目配置：影响多语言字典、语言顺序、分类选项和 TabBar 文案。
const config = require('../config');

// 默认语言：由 config.js 统一维护，影响页面初始化语言。
const DEFAULT_LANGUAGE = config.DEFAULT_LANGUAGE;

// 语言顺序：由 config.js 统一维护，影响语言切换按钮的下一项。
const LANGUAGE_ORDER = config.LANGUAGE_ORDER;

// 多语言字典：由 config.js 统一维护，影响所有界面文案。
const dictionaries = config.I18N_DICTIONARIES;

// 规范化语言编码：避免后端或缓存返回 en、空值等非标准语言时造成字典缺失。
function normalizeLanguage(language) {
  const value = (language || '').trim();
  if (dictionaries[value]) return value;
  if (value.toLowerCase().startsWith('en')) return 'en-US';
  return DEFAULT_LANGUAGE;
}

// 获取当前语言：优先读本地缓存，其次读用户资料，最后读全局状态。
function currentLanguage() {
  const stored = wx.getStorageSync(config.STORAGE_KEYS.language);
  if (stored) return normalizeLanguage(stored);
  const user = wx.getStorageSync(config.STORAGE_KEYS.user);
  if (user && user.language) return normalizeLanguage(user.language);
  try {
    const app = getApp();
    if (app && app.globalData && app.globalData.language) {
      return normalizeLanguage(app.globalData.language);
    }
  } catch (error) {
    return DEFAULT_LANGUAGE;
  }
  return DEFAULT_LANGUAGE;
}

// 设置当前语言：同步写入缓存和全局状态，影响后续所有页面文案。
function setLanguage(language) {
  const normalized = normalizeLanguage(language);
  wx.setStorageSync(config.STORAGE_KEYS.language, normalized);
  try {
    const app = getApp();
    if (app && app.globalData) app.globalData.language = normalized;
  } catch (error) {
    return normalized;
  }
  return normalized;
}

// 计算下一种语言：影响我的页语言切换按钮的循环结果。
function nextLanguage(language) {
  const current = normalizeLanguage(language);
  const index = LANGUAGE_ORDER.indexOf(current);
  return LANGUAGE_ORDER[(index + 1) % LANGUAGE_ORDER.length];
}

// 获取指定语言字典：影响页面 data.text 的内容来源。
function text(language) {
  return dictionaries[normalizeLanguage(language)] || dictionaries[DEFAULT_LANGUAGE];
}

// 获取辅助分类选项：影响首页和拍摄页的分类按钮。
function categoryOptions(language) {
  const dict = text(language);
  return config.CATEGORY_OPTIONS.map((item) => {
    return {
      label: dict[item.labelKey],
      value: item.value
    };
  });
}

// 判断分类是否匹配别名：影响后端返回分类值时的本地化映射。
function matchesCategory(raw, normalized, rule) {
  return rule.exact.indexOf(raw) > -1
    || rule.exact.indexOf(normalized) > -1
    || rule.contains.some((keyword) => normalized.indexOf(keyword) > -1);
}

// 获取分类展示名：影响花色卡片和详情页的分类标签。
function categoryLabel(value, language) {
  const raw = (value || '').trim();
  if (!raw) return text(language).plain;
  const dict = text(language);
  const normalized = raw.toLowerCase();
  const aliasKeys = Object.keys(config.CATEGORY_ALIASES);
  for (let index = 0; index < aliasKeys.length; index += 1) {
    const key = aliasKeys[index];
    if (matchesCategory(raw, normalized, config.CATEGORY_ALIASES[key])) {
      return dict[config.CATEGORY_LABEL_KEYS[key]];
    }
  }
  return raw;
}

// 应用底部导航文案：影响语言切换后 TabBar 的即时显示。
function applyTabBar(language) {
  const dict = text(language);
  config.TAB_BAR_LABEL_KEYS.forEach((labelKey, index) => {
    try {
      wx.setTabBarItem({ index, text: dict[labelKey] });
    } catch (error) {
      // 部分开发者工具场景中，页面会早于 tabbar 就绪，此处保持静默兜底。
    }
  });
}

module.exports = {
  DEFAULT_LANGUAGE,
  LANGUAGE_ORDER,
  normalizeLanguage,
  currentLanguage,
  setLanguage,
  nextLanguage,
  text,
  categoryOptions,
  categoryLabel,
  applyTabBar
};
